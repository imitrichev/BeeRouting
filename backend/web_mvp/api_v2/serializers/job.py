"""Контракты API: job."""
from __future__ import annotations

from typing import Any
from rest_framework import serializers
from backend.optimization import Priority, TaskStatus, VehicleType, WorkType, hhmm_to_minutes


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
