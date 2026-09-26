"""ViewSet'ы CRUD для Job (заявка)."""

from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.viewsets import ModelViewSet

from backend.optimization import TaskStatus

from backend.web_mvp.api_v2.utils.mixins import (
    ACTIONS, MultiSerializerViewSet, PersistentTerritoryMutationMixin,
)

from ..models import Job, Territory
from ..serializers import (
    GeocodeAddressSerializer,
    JobCreateSerializer,
    JobSerializer,
    TaskCreateSerializer,
    TaskStatusUpdateSerializer,
)
from ..services import restore, save
from ..utils.request_context import api_view, optimization_service


# ---------------------------------------------------------------------------
# Фильтры
# ---------------------------------------------------------------------------

class JobFilterSet(filters.FilterSet):
    territory = filters.CharFilter(field_name="territory__code")
    district = filters.CharFilter(field_name="district__name", lookup_expr="icontains")
    skill_required = filters.CharFilter(field_name="skill_required__code")
    priority = filters.CharFilter(field_name="priority__code")
    reference_status = filters.CharFilter(field_name="reference_status")

    class Meta:
        model = Job
        fields = [
            "territory", "district", "skill_required",
            "priority", "reference_status", "gigabit",
        ]


# ---------------------------------------------------------------------------
# Job (заявка)
# ---------------------------------------------------------------------------

class JobViewSet(
    PersistentTerritoryMutationMixin,
    ModelViewSet,
    MultiSerializerViewSet,
):
    """CRUD по заявкам с раздельными сериалайзерами на чтение/запись."""

    queryset = Job.objects.select_related(
        "territory", "district", "skill_required", "priority",
        "required_vehicle", "time_norm", "reference_engineer",
    ).all()
    serializer_class = JobSerializer
    serializers_class = {
        ACTIONS.LIST: JobSerializer,
        ACTIONS.RETRIEVE: JobSerializer,
        ACTIONS.POST: JobCreateSerializer,
        ACTIONS.PUT: JobCreateSerializer,
        ACTIONS.PATCH: JobCreateSerializer,
    }
    filter_backends = [DjangoFilterBackend]
    filterset_class = JobFilterSet

    @action(detail=False, methods=["patch"], url_path="status")
    def update_status(self, request: Request) -> Response:
        """Меняет статус заявки и не запускает перепланирование."""
        serializer = TaskStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        territory_code = request.query_params.get("territory")
        if not territory_code:
            return Response(
                {"error": "Укажите territory в строке запроса."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                territory = Territory.objects.select_for_update().get(
                    code=territory_code
                )
                service = restore(territory)
                service.update_task_status(
                    serializer.validated_data["task_id"],
                    TaskStatus(serializer.validated_data["status"]),
                )
                payload = save(territory, service)
        except Territory.DoesNotExist:
            return Response({"error": "Район не загружен."}, status=404)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=422)
        return Response(payload)


@api_view(["POST"])
def create_task_view(request: Request) -> Response:
    """Создаёт заявку через domain-сервис и сохраняет её в текущем районе."""
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
    """Преобразует введённый адрес в координаты через Nominatim."""
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
