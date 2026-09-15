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
    UnassignedReason,
    UnassignedReasonCode,
    VehicleResource,
    VehicleType,
    hhmm_to_minutes,
    minutes_to_hhmm,
)
from .ortools_optimizer import ORToolsOptimizer
from .routing_provider import InMemoryRoutingProvider, RoutingProvider

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
    "RouteOptimizer",
    "RouteStop",
    "InMemoryRoutingProvider",
    "RoutingProvider",
    "Task",
    "Priority",
    "Skill",
    "UnassignedReason",
    "UnassignedReasonCode",
    "VehicleResource",
    "VehicleType",
    "hhmm_to_minutes",
    "minutes_to_hhmm",
]
