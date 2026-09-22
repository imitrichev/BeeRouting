"""Минимальные REST views без бизнес-логики оптимизации."""

from django.conf import settings
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


@api_view(["POST"])
def explain_task_view(request: Request, task_id: str) -> Response:
    """Возвращает JSON-проверки и человекочитаемое объяснение заявки."""
    try:
        trace, explanation = optimization_service.explain_current_task(task_id)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except Exception as exc:  # noqa: BLE001: внешний LLM-провайдер может вернуть разные ошибки.
        return Response(
            {"error": f"Не удалось получить объяснение от LLM: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    payload = {
        "task_id": task_id,
        "explanation": explanation,
        "developer_mode": settings.DEVELOPER_MODE,
    }
    # В production внутренние проверки не только скрыты компонентом Vue, но и
    # вообще не передаются клиенту. Это исключает их просмотр через DevTools.
    if settings.DEVELOPER_MODE:
        payload["decision_trace"] = trace
    return Response(payload)
