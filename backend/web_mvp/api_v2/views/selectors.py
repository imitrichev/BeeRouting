"""Списки выбора для API v2."""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..models import (
    District,
    Priority,
    Skill,
    Territory,
    TimeNorm,
    VehicleType,
)
from ..serializers.helpers import (
    SkillSerializer,
    VehicleTypeSerializer,
    PrioritySerializer,
    TimeNormSerializer,
    DistrictSerializer,
    TerritorySerializer
)

__all__ = [
    "skill_list",
    "vehicle_type_list",
    "priority_list",
    "time_norm_list",
    "district_list",
    "territory_list"
]

@api_view(["GET"])
def skill_list(request):
    """Список навыков."""
    skills = Skill.objects.all()
    serializer = SkillSerializer(skills, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def vehicle_type_list(request):
    """Список типов транспорта."""
    vehicle_types = VehicleType.objects.all()
    serializer = VehicleTypeSerializer(vehicle_types, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def priority_list(request):
    """Список приоритетов."""
    priorities = Priority.objects.all()
    serializer = PrioritySerializer(priorities, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def time_norm_list(request):
    """Список нормативов времени."""
    time_norms = TimeNorm.objects.all()
    serializer = TimeNormSerializer(time_norms, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def district_list(request):
    """Список районов."""
    districts = District.objects.all()
    serializer = DistrictSerializer(districts, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def territory_list(request):
    """Список территорий."""
    territories = Territory.objects.all()
    serializer = TerritorySerializer(territories, many=True)
    return Response(serializer.data)