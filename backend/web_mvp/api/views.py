"""Минимальные REST views без бизнес-логики оптимизации."""

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status

from backend.optimization import RoutingProviderError

from .services import optimization_service


@api_view(["GET"])
def dataset_view(request: Request) -> Response:
    """Возвращает текущий dataset для экрана приложения."""
    scenario = optimization_service.current_dataset()
    return Response(optimization_service.serialize_response(scenario))


@api_view(["GET"])
def official_dataset_view(request: Request) -> Response:
    """Загружает официальный dataset и возвращает его описание."""
    scenario = optimization_service.load_official_dataset()
    return Response(optimization_service.serialize_response(scenario))


@api_view(["POST"])
def upload_dataset_view(request: Request) -> Response:
    """Принимает multipart-файл с JSON-сценарием."""
    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        return Response(
            {"error": "Передайте JSON-файл в поле file."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        scenario = optimization_service.load_uploaded_dataset(
            uploaded_file.read(), uploaded_file.name
        )
    except (ValueError, RoutingProviderError) as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(optimization_service.serialize_response(scenario))


@api_view(["POST"])
def optimize_view(request: Request) -> Response:
    """Запускает OR-Tools и возвращает маршруты, метрики и причины отказа."""
    try:
        scenario, result = optimization_service.optimize_current()
    except (ValueError, RoutingProviderError) as exc:
        return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    return Response(optimization_service.serialize_response(scenario, result))
