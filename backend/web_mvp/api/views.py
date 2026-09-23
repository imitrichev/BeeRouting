"""Минимальные REST views без бизнес-логики оптимизации."""

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status

from backend.optimization import EngineerOperationalState, RoutingProviderError

from .services import optimization_service
from .serializers import (
    OperationalStateSerializer,
    ReplanningEventSerializer,
    ManualReassignmentConfirmSerializer,
    ManualReassignmentPreviewSerializer,
    TaskCreateSerializer,
    GeocodeAddressSerializer,
)


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


@api_view(["POST"])
def optimize_view(request: Request) -> Response:
    """Запускает OR-Tools и возвращает маршруты, метрики и причины отказа."""
    # Переключатель frontend передаёт только ignore_task_statuses. В режиме
    # уважения статусов обычные ASSIGNED должны сохраняться автоматически;
    # отдельный старый параметр оставлен для обратной совместимости API.
    preserve_assigned_tasks = request.data.get("preserve_assigned_tasks")
    ignore_task_statuses = request.data.get("ignore_task_statuses", False)
    planning_time = request.data.get("planning_time")
    state_serializer = OperationalStateSerializer(
        data=request.data.get("operational_states", []), many=True
    )
    state_serializer.is_valid(raise_exception=True)
    operational_states = tuple(
        EngineerOperationalState(**item) for item in state_serializer.validated_data
    )
    if preserve_assigned_tasks is None:
        preserve_assigned_tasks = not ignore_task_statuses
    if not isinstance(preserve_assigned_tasks, bool):
        return Response(
            {"error": "preserve_assigned_tasks должен быть bool."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(ignore_task_statuses, bool):
        return Response(
            {"error": "ignore_task_statuses должен быть bool."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        scenario, result = optimization_service.optimize_current(
            preserve_assigned_tasks=preserve_assigned_tasks,
            ignore_task_statuses=ignore_task_statuses,
            planning_time=planning_time,
            operational_states=operational_states,
        )
    except (ValueError, RoutingProviderError) as exc:
        return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    return Response(optimization_service.serialize_response(scenario, result))


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
