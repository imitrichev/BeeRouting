"""Сериалайзеры для сущности Engineer"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from ..models import (
    District,
    Engineer,
    Job,
    Priority,
    RescheduleEvent,
    Skill,
    Territory,
    TimeNorm,
    VehicleType,
)

from .helpers import (
    SkillSerializer,
    VehicleTypeSerializer,
    PrioritySerializer,
    TimeNormSerializer,
    DistrictSerializer,
    EngineerBriefSerializer,
)

TIME_INPUT_FORMATS = ["%H:%M", "%H:%M:%S"]


# ---------------------------------------------------------------------------
# Engineer (оператор)
# ---------------------------------------------------------------------------

class EngineerSerializer(serializers.ModelSerializer):
    """Чтение оператора с развёрнутыми связанными сущностями."""

    territory = serializers.SlugRelatedField(slug_field="code", read_only=True)
    vehicle_type = VehicleTypeSerializer(read_only=True)
    skills = SkillSerializer(many=True, read_only=True)

    shift_start = serializers.TimeField(format="%H:%M")
    shift_end = serializers.TimeField(format="%H:%M")

    class Meta:
        model = Engineer
        fields = [
            "id", "engineer_id", "territory", "name",
            "start_lat", "start_lon", "shift_start", "shift_end",
            "skills", "vehicle_type",
        ]


class EngineerCreateSerializer(serializers.ModelSerializer):
    """Создание/обновление оператора по "человеческим" ключам связей.

    Территория и транспорт передаются кодом (``territory``,
    ``vehicle_type``), навыки — списком кодов (``skills``).
    """

    territory = serializers.SlugRelatedField(
        slug_field="code", queryset=Territory.objects.all(),
    )
    vehicle_type = serializers.SlugRelatedField(
        slug_field="code", queryset=VehicleType.objects.all(),
    )
    skills = serializers.SlugRelatedField(
        slug_field="code", queryset=Skill.objects.all(), many=True,
    )

    shift_start = serializers.TimeField(input_formats=TIME_INPUT_FORMATS)
    shift_end = serializers.TimeField(input_formats=TIME_INPUT_FORMATS)

    class Meta:
        model = Engineer
        fields = [
            "engineer_id", "territory", "name",
            "start_lat", "start_lon", "shift_start", "shift_end",
            "skills", "vehicle_type",
        ]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        shift_start = attrs.get("shift_start", getattr(self.instance, "shift_start", None))
        shift_end = attrs.get("shift_end", getattr(self.instance, "shift_end", None))
        if shift_start and shift_end and shift_start >= shift_end:
            raise serializers.ValidationError(
                "shift_end должен быть позже shift_start."
            )
        skills = attrs.get("skills")
        if skills is not None and not (1 <= len(skills) <= 3):
            raise serializers.ValidationError(
                {"skills": "У оператора должно быть от 1 до 3 навыков."}
            )
        return attrs

    def to_representation(self, instance: Engineer) -> dict[str, Any]:
        """После создания/обновления отдаём полное read-представление."""
        return EngineerSerializer(instance, context=self.context).data