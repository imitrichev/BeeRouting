"""Минимальные REST views без бизнес-логики оптимизации."""

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status

from backend.optimization import RoutingProviderError

from ..services.optimization import optimization_service


@api_view(["GET"])
def dataset_view(request: Request) -> Response:
    """Возвращает текущий dataset для экрана приложения."""
    scenario = optimization_service.current_dataset()
    return Response(optimization_service.serialize_response(scenario))


@api_view(["POST"])
def load_territory_dataset_view(request: Request) -> Response:
    """Делает dataset'ом указанную территорию и возвращает его описание."""
    territory_code = request.data.get("territory_code")
    if not territory_code:
        return Response(
            {"error": "Передайте код территории в поле territory_code."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        scenario = optimization_service.load_territory(territory_code)
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