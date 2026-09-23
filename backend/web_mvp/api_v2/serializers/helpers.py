"""Вспомогательные "плоские" сериалайзеры для вложенного отображения"""

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


class TerritorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Territory
        fields = ["code", "name"]
