"""ViewSet'ы CRUD для RescheduleEvent (событие перепланирования)."""

from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from backend.web_mvp.api_v2.utils.mixins import ACTIONS, MultiSerializerViewSet

from ..models import RescheduleEvent
from ..serializers import (
    RescheduleEventCreateSerializer,
    RescheduleEventSerializer,
)


# ---------------------------------------------------------------------------
# Фильтры
# ---------------------------------------------------------------------------

class RescheduleEventFilterSet(filters.FilterSet):
    territory = filters.CharFilter(field_name="territory__code")
    event_type = filters.CharFilter(field_name="event_type")

    class Meta:
        model = RescheduleEvent
        fields = ["territory", "event_type"]


# ---------------------------------------------------------------------------
# RescheduleEvent (событие перепланирования)
# ---------------------------------------------------------------------------

class RescheduleEventViewSet(
    ModelViewSet,
    MultiSerializerViewSet,
):
    """CRUD по событиям перепланирования с раздельными сериалайзерами."""

    queryset = RescheduleEvent.objects.select_related(
        "territory", "job", "engineer",
    ).all()
    permission_classes = [IsAuthenticated]
    serializer_class = RescheduleEventSerializer
    serializers_class = {
        ACTIONS.LIST: RescheduleEventSerializer,
        ACTIONS.RETRIEVE: RescheduleEventSerializer,
        ACTIONS.POST: RescheduleEventCreateSerializer,
        ACTIONS.PUT: RescheduleEventCreateSerializer,
        ACTIONS.PATCH: RescheduleEventCreateSerializer,
    }
    filter_backends = [DjangoFilterBackend]
    filterset_class = RescheduleEventFilterSet
