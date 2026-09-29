"""Независимое математическое ядро оптимизации маршрутов."""

from .config import ICORoutingConfig, OptimizerConfig
from .ico_optimizer import ICOOptimizer
from .baseline_optimizer import GreedyBaselineOptimizer
from .interfaces import RouteOptimizer
from .models import (
    Engineer,
    EngineerAvailability,
    EngineerOperationalState,
    EngineerRoute,
    EquipmentResource,
    OptimizationProblem,
    OptimizationResult,
    RouteStop,
    Priority,
    Skill,
    Task,
    TaskStatus,
    UnassignedReason,
    UnassignedReasonCode,
    VehicleResource,
    VehicleType,
    hhmm_to_minutes,
    minutes_to_hhmm,
)
from .ortools_optimizer import ORToolsOptimizer
from .timefold_optimizer import TimefoldOptimizer, TimefoldUnavailableError
from .manual_planner import (
    ControlDataset,
    ManualAssignment,
    ManualAssignmentError,
    ManualAssignmentPlan,
    ManualAssignmentPlanner,
    ManualAssignmentValidation,
    ManualAssignmentViolation,
    load_control_dataset,
    load_control_dataset_from_scenario,
)
from .routing_provider import (
    CoordinateRoutingProvider,
    InMemoryRoutingProvider,
    OSRMRoutingProvider,
    create_osrm_provider_from_environment,
    RoutingProviderError,
    RoutingProvider,
)
from .otp_routing import (
    OTPRoute,
    OTPRouteCache,
    OTPRoutingClient,
    create_otp_client_from_environment,
)
from .json_import import (
    JsonScenario,
    load_json_scenario,
    load_json_scenario_data,
    load_problem_from_json,
)
from .explanation import ExplanationEngine
from .work_norms import WORK_NORMS, WorkNorm, WorkType

__all__ = [
    "Engineer",
    "EngineerAvailability",
    "EngineerOperationalState",
    "EngineerRoute",
    "EquipmentResource",
    "OptimizerConfig",
    "ICORoutingConfig",
    "ICOOptimizer",
    "GreedyBaselineOptimizer",
    "OptimizationProblem",
    "OptimizationResult",
    "ORToolsOptimizer",
    "TimefoldOptimizer",
    "TimefoldUnavailableError",
    "ControlDataset",
    "ManualAssignment",
    "ManualAssignmentError",
    "ManualAssignmentPlan",
    "ManualAssignmentPlanner",
    "ManualAssignmentValidation",
    "ManualAssignmentViolation",
    "load_control_dataset",
    "load_control_dataset_from_scenario",
    "RouteOptimizer",
    "RouteStop",
    "InMemoryRoutingProvider",
    "CoordinateRoutingProvider",
    "OSRMRoutingProvider",
    "OTPRoute",
    "OTPRouteCache",
    "OTPRoutingClient",
    "create_otp_client_from_environment",
    "create_osrm_provider_from_environment",
    "RoutingProviderError",
    "RoutingProvider",
    "Task",
    "TaskStatus",
    "Priority",
    "Skill",
    "UnassignedReason",
    "UnassignedReasonCode",
    "VehicleResource",
    "VehicleType",
    "hhmm_to_minutes",
    "minutes_to_hhmm",
    "JsonScenario",
    "load_json_scenario",
    "load_json_scenario_data",
    "load_problem_from_json",
    "ExplanationEngine",
    "WORK_NORMS",
    "WorkNorm",
    "WorkType",
]
