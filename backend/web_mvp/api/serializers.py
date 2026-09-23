from __future__ import annotations

from typing import Any

from rest_framework import serializers

from backend.optimization import (
    JsonScenario,
    OptimizationResult,
    Priority,
    Skill,
    TaskStatus,
    VehicleType,
    WorkType,
    hhmm_to_minutes,
)


class TaskCreateSerializer(serializers.Serializer):
    """Проверяет поля новой заявки до передачи в domain-модель."""

    id = serializers.CharField(max_length=120)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    work_type = serializers.ChoiceField(choices=[item.value for item in WorkType])
    window_start = serializers.RegexField(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    window_end = serializers.RegexField(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    priority = serializers.ChoiceField(
        choices=[item.value for item in Priority], default=Priority.NORMAL.value
    )
    required_vehicle_type = serializers.ChoiceField(
        choices=[item.value for item in VehicleType], required=False, allow_null=True
    )
    required_equipment = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, default=list
    )
    status = serializers.ChoiceField(
        choices=[TaskStatus.NOT_SENT.value, TaskStatus.OVERDUE.value],
        default=TaskStatus.NOT_SENT.value,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Проверяет настоящее время в 24-часовом формате и порядок окна."""
        try:
            start = hhmm_to_minutes(attrs["window_start"])
            end = hhmm_to_minutes(attrs["window_end"])
        except ValueError as exc:
            raise serializers.ValidationError(
                {"window_start": "Используйте время HH:MM в 24-часовом формате."}
            ) from exc
        if end <= start:
            raise serializers.ValidationError(
                {"window_end": "Конец окна должен быть позже начала."}
            )
        return attrs


class GeocodeAddressSerializer(serializers.Serializer):
    """Проверяет адрес, введённый диспетчером."""

    address = serializers.CharField(max_length=500, trim_whitespace=True)


class OperationalStateSerializer(serializers.Serializer):
    """Проверяет фактическое состояние инженера для перепланирования."""

    engineer_id = serializers.CharField()
    current_location_id = serializers.CharField()
    remaining_service_minutes = serializers.IntegerField(
        min_value=0, required=False, allow_null=True
    )


class ReplanningEventSerializer(serializers.Serializer):
    """Проверяет одно из трёх поддерживаемых событий перепланирования."""

    event_type = serializers.ChoiceField(
        choices=("ENGINEER_UNAVAILABLE", "EMERGENCY_TASK", "TASK_CANCELLED")
    )
    planning_time = serializers.RegexField(r"^\d{2}:\d{2}$")
    engineer_id = serializers.CharField(required=False)
    task_id = serializers.CharField(required=False)
    task = TaskCreateSerializer(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Требует payload, соответствующий выбранному типу события."""
        event_type = attrs["event_type"]
        required_field = {
            "ENGINEER_UNAVAILABLE": "engineer_id",
            "EMERGENCY_TASK": "task",
            "TASK_CANCELLED": "task_id",
        }[event_type]
        if not attrs.get(required_field):
            raise serializers.ValidationError(
                {required_field: "Поле обязательно для выбранного события."}
            )
        return attrs


class ManualReassignmentPreviewSerializer(serializers.Serializer):
    """Проверяет запрос предварительного ручного переназначения."""

    task_id = serializers.CharField(max_length=120)
    engineer_id = serializers.CharField(max_length=120)


class ManualReassignmentConfirmSerializer(serializers.Serializer):
    """Проверяет подтверждение ранее рассчитанного переназначения."""

    proposal_id = serializers.CharField(max_length=64)


class RouteStopSerializer(serializers.Serializer):
    task_id = serializers.ReadOnlyField()
    latitude = serializers.FloatField(read_only=True)
    longitude = serializers.FloatField(read_only=True)

    arrival_time = serializers.ReadOnlyField()
    service_start_time = serializers.ReadOnlyField()
    service_end_time = serializers.ReadOnlyField()

    travel_time_from_previous = serializers.FloatField(read_only=True)
    distance_from_previous_km = serializers.FloatField(read_only=True)

    def to_representation(self, stop: Any) -> dict[str, Any]:
        tasks_by_id: dict[Any, Any] = self.context["tasks_by_id"]
        task = tasks_by_id[stop.task_id]

        return {
            "task_id": stop.task_id,
            "latitude": task.latitude,
            "longitude": task.longitude,
            "arrival_time": stop.arrival_time,
            "service_start_time": stop.service_start_time,
            "service_end_time": stop.service_end_time,
            "travel_time_from_previous": stop.travel_time_from_previous,
            "distance_from_previous_km": stop.distance_from_previous_km,
        }


class EngineerRouteSerializer(serializers.Serializer):
    engineer_id = serializers.ReadOnlyField()
    engineer_name = serializers.CharField(read_only=True)
    vehicle_type = serializers.CharField(read_only=True)

    start_latitude = serializers.FloatField(read_only=True)
    start_longitude = serializers.FloatField(read_only=True)

    total_distance_km = serializers.FloatField(read_only=True)
    total_travel_minutes = serializers.FloatField(read_only=True)

    geometry = serializers.JSONField(read_only=True, allow_null=True)
    stops = RouteStopSerializer(many=True, read_only=True)

    def to_representation(
        self,
        route_item: tuple[Any, Any],
    ) -> dict[str, Any]:
        engineer_id, route = route_item

        engineers_by_id: dict[Any, Any] = self.context["engineers_by_id"]
        tasks_by_id: dict[Any, Any] = self.context["tasks_by_id"]
        routing_provider = self.context.get("routing_provider")
        problem = self.context.get("problem")

        engineer = engineers_by_id[engineer_id]
        start_location_id = (
            problem.route_start_location(engineer)
            if problem is not None
            else engineer.start_location_id
        )
        start_coordinates = self.context["scenario"].location_coordinates.get(
            start_location_id
        )

        location_ids = [
            start_location_id,
            *[
                tasks_by_id[stop.task_id].location_id
                for stop in route.stops
            ],
        ]

        geometry = (
            routing_provider.get_route_geometry(
                location_ids,
                engineer.vehicle_type,
            )
            if routing_provider is not None
            else None
        )

        return {
            "engineer_id": engineer_id,
            "engineer_name": engineer.name,
            "vehicle_type": engineer.vehicle_type.value,
            "start_latitude": (
                start_coordinates[0] if start_coordinates else engineer.start_latitude
            ),
            "start_longitude": (
                start_coordinates[1] if start_coordinates else engineer.start_longitude
            ),
            "total_distance_km": route.total_distance_km,
            "total_travel_minutes": route.total_travel_minutes,
            "geometry": geometry,
            "stops": RouteStopSerializer(
                route.stops,
                many=True,
                context=self.context,
            ).data,
        }


class UnassignedTaskSerializer(serializers.Serializer):
    task_id = serializers.ReadOnlyField()
    reason_code = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)

    def to_representation(
        self,
        unassigned_item: tuple[Any, Any],
    ) -> dict[str, Any]:
        task_id, reason = unassigned_item

        return {
            "task_id": task_id,
            "reason_code": reason.code.value,
            "message": reason.message,
        }


class OptimizationMetricsSerializer(serializers.Serializer):
    assigned_task_count = serializers.IntegerField(read_only=True)
    unassigned_task_count = serializers.IntegerField(read_only=True)
    used_engineers_count = serializers.IntegerField(read_only=True)

    total_distance_km = serializers.FloatField(
        source="total_distance",
        read_only=True,
    )
    total_travel_minutes = serializers.FloatField(
        source="total_travel_time",
        read_only=True,
    )
    total_objective = serializers.FloatField(read_only=True)

    unassigned_penalty = serializers.FloatField(read_only=True)
    used_engineers_penalty = serializers.FloatField(read_only=True)
    distance_penalty = serializers.FloatField(read_only=True)
    travel_time_penalty = serializers.FloatField(read_only=True)
    plan_disruption_penalty = serializers.FloatField(read_only=True)
    reassigned_task_count = serializers.IntegerField(read_only=True)
    reordered_task_count = serializers.IntegerField(read_only=True)


class OptimizationResultSerializer(serializers.Serializer):
    """
    Read-only serializer для OptimizationResult.

    Required context:
        scenario: JsonScenario

    Optional context:
        routing_provider: провайдер маршрутизации с методом
        get_route_geometry(location_ids, vehicle_type).
    """

    metrics = OptimizationMetricsSerializer(read_only=True)

    distance_by_engineer = serializers.DictField(
        child=serializers.FloatField(),
        read_only=True,
    )
    travel_time_by_engineer = serializers.DictField(
        child=serializers.FloatField(),
        read_only=True,
    )

    routes = EngineerRouteSerializer(many=True, read_only=True)
    unassigned = UnassignedTaskSerializer(many=True, read_only=True)

    def to_representation(
        self,
        result: OptimizationResult,
    ) -> dict[str, Any]:
        scenario: JsonScenario = self.context["scenario"]

        context = {
            **self.context,
            "engineers_by_id": {
                engineer.id: engineer
                for engineer in scenario.engineers
            },
            "tasks_by_id": {
                task.id: task
                for task in scenario.tasks
            },
        }

        return {
            "metrics": OptimizationMetricsSerializer(result).data,
            "distance_by_engineer": result.distance_by_engineer,
            "travel_time_by_engineer": result.travel_time_by_engineer,
            "routes": EngineerRouteSerializer(
                list(result.routes.items()),
                many=True,
                context=context,
            ).data,
            "unassigned": UnassignedTaskSerializer(
                list(result.unassigned_reasons.items()),
                many=True,
                context=context,
            ).data,
        }

class DatasetTaskSerializer(serializers.Serializer):
    id = serializers.ReadOnlyField()
    location_id = serializers.ReadOnlyField()
    status = serializers.SerializerMethodField()
    current_engineer_id = serializers.ReadOnlyField()

    latitude = serializers.FloatField(read_only=True)
    longitude = serializers.FloatField(read_only=True)
    address = serializers.CharField(read_only=True, allow_null=True)

    required_skill = serializers.SerializerMethodField()
    duration_minutes = serializers.IntegerField(read_only=True)

    window_start = serializers.ReadOnlyField()
    window_end = serializers.ReadOnlyField()

    priority = serializers.SerializerMethodField()
    required_vehicle_type = serializers.SerializerMethodField()
    required_equipment = serializers.SerializerMethodField()
    is_plannable = serializers.SerializerMethodField()
    assignment_locked = serializers.SerializerMethodField()

    @staticmethod
    def get_required_skill(task: Any) -> str:
        return next(iter(task.required_skills)).value

    @staticmethod
    def get_status(task: Any) -> str:
        """Возвращает нормализованный статус domain-модели для API."""
        return task.status.value

    def get_is_plannable(self, task: Any) -> bool:
        """Показывает, участвует ли заявка в выбранном режиме расчёта."""
        if self.context.get("ignore_task_statuses", False):
            return True
        return task.status.value not in {"CANCELLED", "COMPLETED"}

    def get_assignment_locked(self, task: Any) -> bool:
        """Показывает, запрещено ли solver менять текущего исполнителя."""
        if self.context.get("ignore_task_statuses", False):
            return False
        if task.status.value in {"EN_ROUTE", "IN_PROGRESS"}:
            return True
        return bool(
            self.context.get("preserve_assigned_tasks", False)
            and task.status.value == "ASSIGNED"
        )

    @staticmethod
    def get_priority(task: Any) -> str:
        return task.priority.value

    @staticmethod
    def get_required_vehicle_type(task: Any) -> str | None:
        if task.required_vehicle_type is None:
            return None

        return task.required_vehicle_type.value

    @staticmethod
    def get_required_equipment(task: Any) -> list[str]:
        """Возвращает стабильный список обязательного оборудования."""
        return sorted(task.required_equipment)


class DatasetEngineerSerializer(serializers.Serializer):
    id = serializers.ReadOnlyField()
    name = serializers.CharField(read_only=True)

    qualifications = serializers.SerializerMethodField()
    vehicle_type = serializers.SerializerMethodField()

    start_location_id = serializers.ReadOnlyField()
    start_address = serializers.SerializerMethodField()
    start_latitude = serializers.FloatField(read_only=True)
    start_longitude = serializers.FloatField(read_only=True)

    available_from = serializers.SerializerMethodField()
    available_until = serializers.SerializerMethodField()

    @staticmethod
    def get_qualifications(engineer: Any) -> list[str]:
        return [
            skill.value
            for skill in engineer.qualifications
        ]

    @staticmethod
    def get_vehicle_type(engineer: Any) -> str:
        return engineer.vehicle_type.value

    def get_start_address(self, engineer: Any) -> str | None:
        """Возвращает адрес офиса из корневого JSON-сценария."""
        return self.root.instance.office_address

    def get_available_from(self, engineer: Any) -> Any:
        availability = self._get_availability(engineer.id)
        return availability.available_from

    def get_available_until(self, engineer: Any) -> Any:
        availability = self._get_availability(engineer.id)
        return availability.available_until

    def _get_availability(self, engineer_id: Any) -> Any:
        """
        Берёт availability из кэша на root-сериализаторе.

        Первая запись для инженера сохраняется намеренно: это повторяет
        исходное поведение next(... for item in scenario.availabilities ...).
        """
        root_serializer = self.root

        if not hasattr(root_serializer, "_availability_by_engineer"):
            scenario = root_serializer.instance

            availability_by_engineer: dict[Any, Any] = {}

            for availability in scenario.availabilities:
                availability_by_engineer.setdefault(
                    availability.engineer_id,
                    availability,
                )

            root_serializer._availability_by_engineer = (
                availability_by_engineer
            )

        try:
            return root_serializer._availability_by_engineer[engineer_id]
        except KeyError as exc:
            raise serializers.ValidationError(
                {
                    "engineer_id": (
                        f"Для инженера {engineer_id!r} "
                        "не найдена availability."
                    ),
                }
            ) from exc


class DatasetSerializer(serializers.Serializer):
    """
    Сериализатор JsonScenario для Vue-таблиц и карты.

    Required context:
        source_name: имя исходного файла, набора данных или источника.
    """

    source_name = serializers.SerializerMethodField()
    scenario_name = serializers.CharField(read_only=True)

    engineers = DatasetEngineerSerializer(
        many=True,
        read_only=True,
    )
    tasks = DatasetTaskSerializer(
        many=True,
        read_only=True,
    )

    def get_source_name(self, scenario: Any) -> str:
        return self.context["source_name"]
