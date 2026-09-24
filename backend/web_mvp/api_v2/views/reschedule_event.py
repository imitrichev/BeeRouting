"""ViewSet'ы CRUD для RescheduleEvent (событие перепланирования)."""

from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status

from backend.optimization import RoutingProviderError
from rest_framework.viewsets import ModelViewSet

from backend.web_mvp.api_v2.utils.mixins import ACTIONS, MultiSerializerViewSet

from ..models import RescheduleEvent
from ..serializers import (
    RescheduleEventCreateSerializer,
    RescheduleEventSerializer,
    ReplanningEventSerializer,
)
from ..utils.request_context import api_view, optimization_service


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


@api_view(["POST"])
def replan_view(request: Request) -> Response:
    """Применяет оперативное событие и возвращает обновлённый план."""
    serializer = ReplanningEventSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        scenario, result, event = optimization_service.replan_current(
            dict(serializer.validated_data)
        )
    except (ValueError, RoutingProviderError) as exc:
        return Response(
            {"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
        )
    payload = optimization_service.serialize_response(scenario, result)
    payload["replanning_event"] = event
    return Response(payload)
