"""Контракты API: helpers."""
from __future__ import annotations

from typing import Any
from rest_framework import serializers


class GeocodeAddressSerializer(serializers.Serializer):
    """Проверяет адрес, введённый диспетчером."""

    address = serializers.CharField(max_length=500, trim_whitespace=True)


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
