"""Обработчики API v2: core."""
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


@drf_api_view(['GET'])
def territories_view(request):
    """Возвращает только уже импортированные районы."""
    return Response(list(Territory.objects.order_by('name').values('code', 'name', 'revision')))

@drf_api_view(['GET'])
def dataset_view(request):
    """Возвращает сохранённую карту и план без обращения к solver и OSRM."""
    territory = Territory.objects.filter(code=request.query_params.get('territory')).first()
    if territory is None:
        return Response({'error': 'Район не загружен.'}, status=404)
    return Response({**territory.response, 'territory_code': territory.code})

@drf_api_view(['GET', 'POST'])
def official_dataset_view(request):
    """Импортирует официальный район один раз, затем открывает сохранённый план."""
    territory = import_dataset(OFFICIAL_DATASET_PATH.read_bytes(), OFFICIAL_DATASET_PATH.name)
    return Response({**territory.response, 'territory_code': territory.code})

@drf_api_view(['POST'])
def upload_dataset_view(request):
    """Добавляет район из пользовательского JSON."""
    uploaded = request.FILES.get('file')
    if uploaded is None:
        return Response({'error': 'Передайте JSON в поле file.'}, status=400)
    try:
        territory = import_dataset(uploaded.read(), uploaded.name)
    except (ValueError, UnicodeError) as exc:
        return Response({'error': str(exc)}, status=400)
    return Response({**territory.response, 'territory_code': territory.code})

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
