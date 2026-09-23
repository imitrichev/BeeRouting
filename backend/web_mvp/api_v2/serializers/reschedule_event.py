"""Контракты API: reschedule_event."""
from __future__ import annotations

from typing import Any
from rest_framework import serializers
from .job import TaskCreateSerializer


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
