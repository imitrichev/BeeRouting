"""Обработчики API v2: reschedule_event."""
from django.conf import settings
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view as drf_api_view
from backend.optimization import EngineerOperationalState, RoutingProviderError
from backend.web_mvp.api.services import OFFICIAL_DATASET_PATH
from ..models import Territory
from ..services import import_dataset
from ..serializers import (OperationalStateSerializer, ReplanningEventSerializer,
    ManualReassignmentConfirmSerializer, ManualReassignmentPreviewSerializer,
    TaskCreateSerializer, GeocodeAddressSerializer)
from .context import api_view, optimization_service


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
        return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    payload = optimization_service.serialize_response(scenario, result)
    payload["replanning_event"] = event
    return Response(payload)
