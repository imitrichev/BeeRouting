"""Независимое математическое ядро оптимизации маршрутов."""

from .config import OptimizerConfig
from .baseline_optimizer import GreedyBaselineOptimizer
from .interfaces import RouteOptimizer
from .models import (
    Engineer,
    EngineerAvailability,
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
)
from .routing_provider import (
    CoordinateRoutingProvider,
    InMemoryRoutingProvider,
    OSRMRoutingProvider,
    RoutingProviderError,
    RoutingProvider,
)
from .json_import import (
    JsonScenario,
    load_json_scenario,
    load_json_scenario_data,
    load_problem_from_json,
)

__all__ = [
    "Engineer",
    "EngineerAvailability",
    "EngineerRoute",
    "EquipmentResource",
    "OptimizerConfig",
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
    "RouteOptimizer",
    "RouteStop",
    "InMemoryRoutingProvider",
    "CoordinateRoutingProvider",
    "OSRMRoutingProvider",
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
]
