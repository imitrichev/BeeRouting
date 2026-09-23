"""Сериалайзеры для сущности Job"""

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
    DistrictSerializer,
    SkillSerializer,
    VehicleTypeSerializer,
    PrioritySerializer,
    TimeNormSerializer,
    EngineerBriefSerializer,
)

TIME_INPUT_FORMATS = ["%H:%M", "%H:%M:%S"]


# ---------------------------------------------------------------------------
# Job (заявка)
# ---------------------------------------------------------------------------

class JobSerializer(serializers.ModelSerializer):
    """Чтение заявки с развёрнутыми связанными сущностями."""

    territory = serializers.SlugRelatedField(slug_field="code", read_only=True)
    district = DistrictSerializer(read_only=True)
    skill_required = SkillSerializer(read_only=True)
    priority = PrioritySerializer(read_only=True)
    required_vehicle = VehicleTypeSerializer(read_only=True)
    time_norm = TimeNormSerializer(read_only=True)
    reference_engineer = EngineerBriefSerializer(read_only=True)

    window_start = serializers.TimeField(format="%H:%M")
    window_end = serializers.TimeField(format="%H:%M")

    class Meta:
        model = Job
        fields = [
            "id", "job_id", "territory", "request_id", "control_request_id",
            "skill_required", "request_type_bk", "request_type_hd",
            "district", "address", "lat", "lon",
            "window_start", "window_end", "duration_min", "time_norm",
            "priority", "required_vehicle", "reference_status",
            "reference_engineer", "gigabit",
        ]


class JobCreateSerializer(serializers.ModelSerializer):
    """Создание/обновление заявки по "человеческим" ключам связей.

    Территория, навык, приоритет, транспорт и норматив передаются кодами
    (``territory``, ``skill_required`` и т.д.), район — названием (создаётся
    автоматически при отсутствии), инженер — его ``engineer_id``.
    """

    territory = serializers.SlugRelatedField(
        slug_field="code", queryset=Territory.objects.all(),
    )
    skill_required = serializers.SlugRelatedField(
        slug_field="code", queryset=Skill.objects.all(),
    )
    priority = serializers.SlugRelatedField(
        slug_field="code", queryset=Priority.objects.all(),
    )
    required_vehicle = serializers.SlugRelatedField(
        slug_field="code", queryset=VehicleType.objects.all(),
        required=False, allow_null=True,
    )
    time_norm = serializers.SlugRelatedField(
        slug_field="code", queryset=TimeNorm.objects.all(),
        required=False, allow_null=True,
    )
    reference_engineer = serializers.SlugRelatedField(
        slug_field="engineer_id", queryset=Engineer.objects.all(),
        required=False, allow_null=True,
    )
    district = serializers.CharField(
        write_only=True, help_text="Название района; создаётся при отсутствии",
    )

    window_start = serializers.TimeField(input_formats=TIME_INPUT_FORMATS)
    window_end = serializers.TimeField(input_formats=TIME_INPUT_FORMATS)

    class Meta:
        model = Job
        fields = [
            "job_id", "territory", "request_id", "control_request_id",
            "skill_required", "request_type_bk", "request_type_hd",
            "district", "address", "lat", "lon",
            "window_start", "window_end", "duration_min", "time_norm",
            "priority", "required_vehicle", "reference_status",
            "reference_engineer", "gigabit",
        ]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        window_start = attrs.get("window_start", getattr(self.instance, "window_start", None))
        window_end = attrs.get("window_end", getattr(self.instance, "window_end", None))
        if window_start and window_end and window_start >= window_end:
            raise serializers.ValidationError(
                "window_end должен быть позже window_start."
            )
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Job:
        district_name = validated_data.pop("district")
        district, _ = District.objects.get_or_create(
            territory=validated_data["territory"], name=district_name,
        )
        return Job.objects.create(district=district, **validated_data)

    def update(self, instance: Job, validated_data: dict[str, Any]) -> Job:
        district_name = validated_data.pop("district", None)
        if district_name is not None:
            territory = validated_data.get("territory", instance.territory)
            district, _ = District.objects.get_or_create(
                territory=territory, name=district_name,
            )
            instance.district = district
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance

    def to_representation(self, instance: Job) -> dict[str, Any]:
        """После создания/обновления отдаём полное read-представление."""
        return JobSerializer(instance, context=self.context).data