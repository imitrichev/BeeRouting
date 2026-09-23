"""Сериалайзеры для сущности RescheduleEvent"""

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