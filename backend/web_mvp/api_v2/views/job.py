"""ViewSet'ы CRUD для Job (заявка)."""

from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from backend.web_mvp.api_v2.utils.mixins import ACTIONS, MultiSerializerViewSet

from ..models import Job
from ..serializers import (
    JobCreateSerializer,
    JobSerializer,
)


# ---------------------------------------------------------------------------
# Фильтры
# ---------------------------------------------------------------------------

class JobFilterSet(filters.FilterSet):
    territory = filters.CharFilter(field_name="territory__code")
    district = filters.CharFilter(field_name="district__name", lookup_expr="icontains")
    skill_required = filters.CharFilter(field_name="skill_required__code")
    priority = filters.CharFilter(field_name="priority__code")
    reference_status = filters.CharFilter(field_name="reference_status")

    class Meta:
        model = Job
        fields = [
            "territory", "district", "skill_required",
            "priority", "reference_status", "gigabit",
        ]


# ---------------------------------------------------------------------------
# Job (заявка)
# ---------------------------------------------------------------------------

class JobViewSet(
    ModelViewSet,
    MultiSerializerViewSet,
):
    """CRUD по заявкам с раздельными сериалайзерами на чтение/запись."""

    queryset = Job.objects.select_related(
        "territory", "district", "skill_required", "priority",
        "required_vehicle", "time_norm", "reference_engineer",
    ).all()
    permission_classes = [IsAuthenticated]
    serializer_class = JobSerializer
    serializers_class = {
        ACTIONS.LIST: JobSerializer,
        ACTIONS.RETRIEVE: JobSerializer,
        ACTIONS.POST: JobCreateSerializer,
        ACTIONS.PUT: JobCreateSerializer,
        ACTIONS.PATCH: JobCreateSerializer,
    }
    filter_backends = [DjangoFilterBackend]
    filterset_class = JobFilterSet
