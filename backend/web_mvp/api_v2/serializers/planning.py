"""Входные контракты оперативного планирования API v2."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from backend.optimization import (
    VehicleType,
    WorkType,
    hhmm_to_minutes,
)


class TaskCreateSerializer(serializers.Serializer):
    """Проверяет новую заявку до передачи в domain-сервис."""

    id = serializers.CharField(max_length=120)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    work_type = serializers.ChoiceField(choices=[item.value for item in WorkType])
    window_start = serializers.RegexField(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    window_end = serializers.RegexField(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    required_vehicle_type = serializers.ChoiceField(
        choices=[item.value for item in VehicleType], required=False, allow_null=True
    )
    required_equipment = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, default=list
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Проверяет формат и порядок границ временного окна."""
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
    """Проверяет фактическую позицию инженера при перепланировании."""

    engineer_id = serializers.CharField()
    current_location_id = serializers.CharField()
    remaining_service_minutes = serializers.IntegerField(
        min_value=0, required=False, allow_null=True
    )


class ReplanningEventSerializer(serializers.Serializer):
    """Проверяет один из трёх поддерживаемых сценариев перепланирования."""

    event_type = serializers.ChoiceField(
        choices=("ENGINEER_UNAVAILABLE", "EMERGENCY_TASK", "TASK_CANCELLED")
    )
    planning_time = serializers.RegexField(r"^\d{2}:\d{2}$")
    engineer_id = serializers.CharField(required=False)
    task_id = serializers.CharField(required=False)
    task = TaskCreateSerializer(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Требует payload, соответствующий выбранному событию."""
        required_field = {
            "ENGINEER_UNAVAILABLE": "engineer_id",
            "EMERGENCY_TASK": "task",
            "TASK_CANCELLED": "task_id",
        }[attrs["event_type"]]
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
