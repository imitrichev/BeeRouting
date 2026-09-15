"""Общий интерфейс для реализаций маршрутизатора."""

from abc import ABC, abstractmethod

from .models import OptimizationProblem, OptimizationResult

# Make abstract class
class RouteOptimizer(ABC):
    """Контракт решателя задачи маршрутизации."""

    @abstractmethod
    def optimize(self, problem: OptimizationProblem) -> OptimizationResult:
        """Строит маршруты для переданной задачи."""
        raise NotImplementedError
