"""ViewSet'ы CRUD для Engineer (оператор)."""

from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.viewsets import ModelViewSet

from backend.web_mvp.api_v2.utils.mixins import ACTIONS, MultiSerializerViewSet

from ..models import Engineer
from ..serializers.engineer import (
    EngineerCreateSerializer,
    EngineerSerializer,
)


# ---------------------------------------------------------------------------
# Фильтры
# ---------------------------------------------------------------------------

class EngineerFilterSet(filters.FilterSet):
    territory = filters.CharFilter(field_name="territory__code")
    vehicle_type = filters.CharFilter(field_name="vehicle_type__code")
    skill = filters.CharFilter(field_name="skills__code")

    class Meta:
        model = Engineer
        fields = ["territory", "vehicle_type", "skill"]


# ---------------------------------------------------------------------------
# Engineer (оператор)
# ---------------------------------------------------------------------------

class EngineerViewSet(
    ModelViewSet,
    MultiSerializerViewSet,
):
    """CRUD по операторам с раздельными сериалайзерами на чтение/запись."""

    queryset = Engineer.objects.select_related(
        "territory", "vehicle_type",
    ).prefetch_related("skills").all()
    serializer_class = EngineerSerializer
    serializers_class = {
        ACTIONS.LIST: EngineerSerializer,
        ACTIONS.RETRIEVE: EngineerSerializer,
        ACTIONS.POST: EngineerCreateSerializer,
        ACTIONS.PUT: EngineerCreateSerializer,
        ACTIONS.PATCH: EngineerCreateSerializer,
    }
    filter_backends = [DjangoFilterBackend]
    filterset_class = EngineerFilterSet
