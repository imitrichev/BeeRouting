"""Обработчики API v2: manual_assignment."""
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
from ..utils.request_context import api_view, optimization_service


@api_view(["POST"])
def manual_reassignment_preview_view(request: Request) -> Response:
    """Проверяет ручной перенос, не изменяя действующий план."""
    serializer = ManualReassignmentPreviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        preview = optimization_service.preview_manual_reassignment(
            **serializer.validated_data
        )
    except (ValueError, RoutingProviderError) as exc:
        return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    response_status = (
        status.HTTP_200_OK
        if preview["feasible"]
        else status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    return Response(preview, status=response_status)

@api_view(["POST"])
def manual_reassignment_confirm_view(request: Request) -> Response:
    """Подтверждает preview и публикует рассчитанный новый план."""
    serializer = ManualReassignmentConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        scenario, result, confirmation = optimization_service.confirm_manual_reassignment(
            serializer.validated_data["proposal_id"]
        )
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    payload = optimization_service.serialize_response(scenario, result)
    payload["manual_reassignment"] = confirmation
    return Response(payload)
