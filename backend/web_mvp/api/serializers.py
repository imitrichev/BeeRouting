from __future__ import annotations

from typing import Any

from rest_framework import serializers

from backend.optimization import (
    JsonScenario,
    OptimizationResult,
)


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

        engineer = engineers_by_id[engineer_id]

        location_ids = [
            engineer.start_location_id,
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
            "start_latitude": engineer.start_latitude,
            "start_longitude": engineer.start_longitude,
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

    latitude = serializers.FloatField(read_only=True)
    longitude = serializers.FloatField(read_only=True)

    required_skill = serializers.SerializerMethodField()
    duration_minutes = serializers.IntegerField(read_only=True)

    window_start = serializers.ReadOnlyField()
    window_end = serializers.ReadOnlyField()

    priority = serializers.SerializerMethodField()
    required_vehicle_type = serializers.SerializerMethodField()

    @staticmethod
    def get_required_skill(task: Any) -> str:
        return next(iter(task.required_skills)).value

    @staticmethod
    def get_status(task: Any) -> str:
        """Возвращает нормализованный статус domain-модели для API."""
        return task.status.value

    @staticmethod
    def get_priority(task: Any) -> str:
        return task.priority.value

    @staticmethod
    def get_required_vehicle_type(task: Any) -> str | None:
        if task.required_vehicle_type is None:
            return None

        return task.required_vehicle_type.value


class DatasetEngineerSerializer(serializers.Serializer):
    id = serializers.ReadOnlyField()
    name = serializers.CharField(read_only=True)

    qualifications = serializers.SerializerMethodField()
    vehicle_type = serializers.SerializerMethodField()

    start_location_id = serializers.ReadOnlyField()
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
