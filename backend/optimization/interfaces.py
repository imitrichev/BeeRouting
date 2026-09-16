"""Общий интерфейс для реализаций маршрутизатора."""

from abc import ABC, abstractmethod

from .models import OptimizationProblem, OptimizationResult

class RouteOptimizer(ABC):
    """Контракт решателя задачи маршрутизации.

    Любая реализация получает одну и ту же предметную задачу и возвращает
    один и тот же ``OptimizationResult``. Благодаря этому baseline и OR-Tools
    можно сравнивать без изменения входных данных.
    """

    @abstractmethod
    def optimize(self, problem: OptimizationProblem) -> OptimizationResult:
        """Строит маршруты для переданной задачи."""
        raise NotImplementedError
