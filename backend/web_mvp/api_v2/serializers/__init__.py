"""Сериалайзеры сущностей Job и RescheduleEvent для GET/CREATE запросов.
Для каждой сущности заведено по два сериалайзера:
    *Serializer        — только чтение (GET), с "развёрнутыми" вложенными
                          объектами, удобными для отображения в UI.
    *CreateSerializer   — запись (POST), принимает связанные объекты по их
                          "человеческим" ключам (code/engineer_id/job_id),
                          а не по внутренним PK.
"""

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

TIME_INPUT_FORMATS = ["%H:%M", "%H:%M:%S"]


# ---------------------------------------------------------------------------
# Вспомогательные "плоские" сериалайзеры для вложенного отображения
# ---------------------------------------------------------------------------

class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ["code", "name"]


class VehicleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleType
        fields = ["code", "name"]


class PrioritySerializer(serializers.ModelSerializer):
    class Meta:
        model = Priority
        fields = ["code", "name"]


class TimeNormSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeNorm
        fields = [
            "code", "name", "road_to_client_min",
            "technical_work_min", "documents_min", "base_norm_min",
        ]


class DistrictSerializer(serializers.ModelSerializer):
    class Meta:
        model = District
        fields = ["id", "name"]


class EngineerBriefSerializer(serializers.ModelSerializer):
    """Компактное представление инженера для вложения в Job/RescheduleEvent."""

    vehicle_type = VehicleTypeSerializer(read_only=True)

    class Meta:
        model = Engineer
        fields = ["engineer_id", "name", "vehicle_type"]


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


# ---------------------------------------------------------------------------
# RescheduleEvent (событие перепланирования)
# ---------------------------------------------------------------------------

class RescheduleEventSerializer(serializers.ModelSerializer):
    """Чтение события с развёрнутыми job/engineer."""

    territory = serializers.SlugRelatedField(slug_field="code", read_only=True)
    job = JobSerializer(read_only=True)
    engineer = EngineerBriefSerializer(read_only=True)
    time = serializers.TimeField(format="%H:%M")

    class Meta:
        model = RescheduleEvent
        fields = [
            "id", "territory", "event_type", "time",
            "job", "engineer", "payload",
        ]


class RescheduleEventCreateSerializer(serializers.ModelSerializer):
    """Создание события. Обязательность job/engineer зависит от event_type:

    - ``urgent_job``            — job не обязателен (создаётся отдельно,
      полезная нагрузка приходит в ``payload``);
    - ``cancel_job``             — обязателен ``job`` (по ``job_id``);
    - ``engineer_unavailable``   — обязателен ``engineer`` (по ``engineer_id``).
    """

    territory = serializers.SlugRelatedField(
        slug_field="code", queryset=Territory.objects.all(),
    )
    job = serializers.SlugRelatedField(
        slug_field="job_id", queryset=Job.objects.all(),
        required=False, allow_null=True,
    )
    engineer = serializers.SlugRelatedField(
        slug_field="engineer_id", queryset=Engineer.objects.all(),
        required=False, allow_null=True,
    )
    time = serializers.TimeField(input_formats=TIME_INPUT_FORMATS)
    payload = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = RescheduleEvent
        fields = ["territory", "event_type", "time", "job", "engineer", "payload"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        event_type = attrs.get("event_type")

        if event_type == RescheduleEvent.TYPE_CANCEL_JOB and not attrs.get("job"):
            raise serializers.ValidationError(
                {"job": "Для события cancel_job обязательно поле job (job_id)."}
            )
        if event_type == RescheduleEvent.TYPE_ENGINEER_UNAVAILABLE and not attrs.get("engineer"):
            raise serializers.ValidationError(
                {"engineer": "Для события engineer_unavailable обязательно "
                             "поле engineer (engineer_id)."}
            )
        if event_type == RescheduleEvent.TYPE_URGENT_JOB and not attrs.get("payload"):
            raise serializers.ValidationError(
                {"payload": "Для события urgent_job обязателен payload "
                            "с описанием новой заявки."}
            )
        return attrs

    def to_representation(self, instance: RescheduleEvent) -> dict[str, Any]:
        return RescheduleEventSerializer(instance, context=self.context).data