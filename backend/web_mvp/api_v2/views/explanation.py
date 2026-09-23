"""Обработчики API v2: explanation."""
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
