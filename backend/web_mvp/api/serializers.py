"""Совместимость старого API: реализации контрактов перенесены в api_v2."""
from backend.web_mvp.api_v2.serializers import (
    TaskCreateSerializer,
    GeocodeAddressSerializer,
    OperationalStateSerializer,
    ReplanningEventSerializer,
    ManualReassignmentPreviewSerializer,
    ManualReassignmentConfirmSerializer,
    RouteStopSerializer,
    EngineerRouteSerializer,
    UnassignedTaskSerializer,
    OptimizationMetricsSerializer,
    OptimizationResultSerializer,
    DatasetTaskSerializer,
    DatasetEngineerSerializer,
    DatasetSerializer,
)
