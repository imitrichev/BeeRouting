"""Контракты API: engineer."""
from __future__ import annotations

from typing import Any
from rest_framework import serializers
from .helpers import RouteStopSerializer


class OperationalStateSerializer(serializers.Serializer):
    """Проверяет фактическое состояние инженера для перепланирования."""

    engineer_id = serializers.CharField()
    current_location_id = serializers.CharField()
    remaining_service_minutes = serializers.IntegerField(
        min_value=0, required=False, allow_null=True
    )


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
