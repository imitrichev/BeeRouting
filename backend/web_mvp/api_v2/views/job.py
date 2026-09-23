"""Обработчики API v2: job."""
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
def create_task_view(request: Request) -> Response:
    """Создаёт новую заявку в текущем dataset локального MVP."""
    serializer = TaskCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        scenario = optimization_service.add_task(dict(serializer.validated_data))
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        optimization_service.serialize_response(scenario),
        status=status.HTTP_201_CREATED,
    )

@api_view(["POST"])
def geocode_address_view(request: Request) -> Response:
    """Преобразует введённый адрес в координаты без приблизительного fallback."""
    serializer = GeocodeAddressSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        latitude, longitude = optimization_service.geocode_address(
            serializer.validated_data["address"]
        )
    except ValueError:
        return Response(
            {"error": "Адрес не найден! Проверьте ввод."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response({"latitude": latitude, "longitude": longitude})
