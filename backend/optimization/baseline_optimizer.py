"""Простой последовательный baseline-планировщик."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import OptimizerConfig
from .constraints import (
    engineer_can_execute_task,
    engineer_has_required_equipment,
    resource_ids_used_for_task,
)
from .interfaces import RouteOptimizer
from .models import (
    Engineer,
    EngineerAvailability,
    EngineerRoute,
    OptimizationProblem,
    OptimizationResult,
    RouteStop,
    Task,
    TaskStatus,
    UnassignedReason,
    UnassignedReasonCode,
    hhmm_to_minutes,
    minutes_to_hhmm,
)


@dataclass(frozen=True, slots=True)
class _ScheduledStop:
    """Промежуточное расписание заявки до преобразования в RouteStop."""

    task: Task  # Заявка, для которой рассчитан этот элемент расписания.
    arrival_time: int  # Время прибытия в минутах от начала суток.
    service_start_time: int  # Время начала работы в минутах от начала суток.
    service_end_time: int  # Время окончания работы в минутах от начала суток.
    distance_from_previous_km: float  # Пробег от предыдущей точки в километрах.


class GreedyBaselineOptimizer(RouteOptimizer):
    """Назначает каждую заявку первому допустимому инженеру.

    Заявки и инженеры просматриваются в порядке входных данных. После
    назначения заявка добавляется в конец маршрута выбранного инженера;
    перестановка уже назначенных заявок не выполняется.
    """

    def __init__(self, config: OptimizerConfig | None = None) -> None:
        """Создаёт baseline с общими весами результата."""
        self.config = config or OptimizerConfig()

    def optimize(self, problem: OptimizationProblem) -> OptimizationResult:
        """Строит жадное допустимое решение без глобального поиска."""
        availability_by_engineer = {
            availability.engineer_id: availability
            for availability in problem.availabilities
        }
        tasks_by_engineer: dict[str, list[Task]] = {
            engineer.id: [] for engineer in problem.engineers
        }
        resource_intervals: dict[str, list[tuple[str, int, int]]] = {}
        routers_used = {engineer.id: 0 for engineer in problem.engineers}
        unassigned_reasons: dict[str, UnassignedReason] = {}

        # Начатая заявка образует неизменяемый первый участок маршрута. После
        # неё обычный baseline продолжает обрабатывать остальные заявки строго
        # в исходном порядке.
        started_task_ids: set[str] = set()
        for task in problem.planning_tasks:
            fixed_engineer_id = problem.fixed_task_engineer_by_id.get(task.id)
            if (
                problem.ignore_task_statuses
                or task.status not in {TaskStatus.EN_ROUTE, TaskStatus.IN_PROGRESS}
            ):
                continue
            started_task_ids.add(task.id)
            engineer = next(
                item for item in problem.engineers if item.id == fixed_engineer_id
            )
            if not engineer_can_execute_task(problem, engineer, task):
                unassigned_reasons[task.id] = self._unassigned_reason(
                    problem, task, availability_by_engineer
                )
                continue
            if (
                problem.consider_equipment
                and routers_used[engineer.id] + task.required_router_count
                > problem.available_router_count_for_planning(engineer)
            ):
                unassigned_reasons[task.id] = self._unassigned_reason(
                    problem, task, availability_by_engineer
                )
                continue
            schedule = self._schedule(
                problem,
                engineer,
                availability_by_engineer[engineer.id],
                [task],
            )
            if schedule is None:
                unassigned_reasons[task.id] = self._unassigned_reason(
                    problem, task, availability_by_engineer
                )
                continue
            tasks_by_engineer[engineer.id].append(task)
            routers_used[engineer.id] += task.required_router_count
            candidate_stop = schedule[-1]
            for resource_id in resource_ids_used_for_task(problem, engineer, task):
                resource_intervals.setdefault(resource_id, []).append(
                    (
                        engineer.id,
                        candidate_stop.service_start_time,
                        candidate_stop.service_end_time,
                    )
                )

        for task in problem.planning_tasks:
            if task.id in started_task_ids:
                continue
            # Этот двойной цикл и есть baseline: порядок задач и инженеров
            # полностью определяется входными кортежами, без перестановки.
            fixed_engineer_id = problem.fixed_task_engineer_by_id.get(task.id)
            candidate_engineers = (
                tuple(
                    engineer
                    for engineer in problem.engineers
                    if engineer.id == fixed_engineer_id
                )
                if fixed_engineer_id is not None
                else problem.engineers
            )
            for engineer in candidate_engineers:
                if not engineer_can_execute_task(problem, engineer, task):
                    continue
                if (
                    problem.consider_equipment
                    and routers_used[engineer.id] + task.required_router_count
                    > problem.available_router_count_for_planning(engineer)
                ):
                    continue
                candidate_tasks = tasks_by_engineer[engineer.id] + [task]
                schedule = self._schedule(
                    problem,
                    engineer,
                    availability_by_engineer[engineer.id],
                    candidate_tasks,
                )
                if schedule is None:
                    continue
                candidate_stop = schedule[-1]
                if not self._resources_are_available(
                    problem,
                    engineer,
                    task,
                    candidate_stop.service_start_time,
                    candidate_stop.service_end_time,
                    resource_intervals,
                ):
                    continue

                tasks_by_engineer[engineer.id].append(task)
                routers_used[engineer.id] += task.required_router_count
                # Запоминаем сервисный интервал каждого ограниченного экземпляра,
                # чтобы следующий инженер не получил его одновременно.
                for resource_id in resource_ids_used_for_task(
                    problem, engineer, task
                ):
                    resource_intervals.setdefault(resource_id, []).append(
                        (
                            engineer.id,
                            candidate_stop.service_start_time,
                            candidate_stop.service_end_time,
                        )
                    )
                break
            else:
                unassigned_reasons[task.id] = self._unassigned_reason(
                    problem, task, availability_by_engineer
                )

        routes: dict[str, EngineerRoute] = {}
        for engineer in problem.engineers:
            schedule = self._schedule(
                problem,
                engineer,
                availability_by_engineer[engineer.id],
                tasks_by_engineer[engineer.id],
            )
            assert schedule is not None
            routes[engineer.id] = self._build_route(
                engineer,
                schedule,
                problem,
            )

        unassigned_task_ids = tuple(
            task.id for task in problem.planning_tasks if task.id in unassigned_reasons
        )
        distance_by_engineer = {
            engineer_id: route.total_distance_km
            for engineer_id, route in routes.items()
        }
        travel_time_by_engineer = {
            engineer_id: route.total_travel_minutes
            for engineer_id, route in routes.items()
        }
        total_distance = math.fsum(distance_by_engineer.values())
        total_travel_time = sum(travel_time_by_engineer.values())
        used_engineers_count = sum(bool(route.stops) for route in routes.values())
        used_engineers_penalty = (
            used_engineers_count * self.config.used_engineers_penalty
        )
        distance_penalty = int(
            round(total_distance * self.config.distance_penalty_per_km)
        )
        unassigned_penalty = sum(
            self.config.unassigned_penalty * self._priority_multiplier(task)
            for task in problem.planning_tasks
            if task.id in unassigned_task_ids
        )
        travel_time_penalty = (
            total_travel_time * self.config.travel_time_penalty_per_minute
        )
        return OptimizationResult(
            routes=routes,
            unassigned_task_ids=unassigned_task_ids,
            unassigned_reasons=unassigned_reasons,
            distance_by_engineer=distance_by_engineer,
            total_distance=total_distance,
            travel_time_by_engineer=travel_time_by_engineer,
            total_travel_time=total_travel_time,
            used_engineers_count=used_engineers_count,
            assigned_task_count=sum(len(route.stops) for route in routes.values()),
            unassigned_task_count=len(unassigned_task_ids),
            total_objective=(
                unassigned_penalty
                + used_engineers_penalty
                + distance_penalty
                + travel_time_penalty
            ),
            total_service_minutes=sum(
                route.total_service_minutes for route in routes.values()
            ),
            unassigned_penalty=unassigned_penalty,
            used_engineers_penalty=used_engineers_penalty,
            distance_penalty=distance_penalty,
            travel_time_penalty=travel_time_penalty,
        )

    def _priority_multiplier(self, task: Task) -> int:
        """Возвращает настроенный вес неназначения по типу работ."""
        return self.config.unassigned_multiplier(task)

    @staticmethod
    def _schedule(
        problem: OptimizationProblem,
        engineer: Engineer,
        availability: EngineerAvailability,
        tasks: list[Task],
    ) -> list[_ScheduledStop] | None:
        """Проверяет последовательный маршрут и возвращает его расписание."""
        # Тип availability намеренно читается через атрибуты модели: метод не
        # меняет domain-модель и использует только её публичные поля.
        current_time = problem.route_start_minutes(availability)
        previous_location = problem.route_start_location(engineer)
        schedule: list[_ScheduledStop] = []
        for task in tasks:
            travel_time = problem.travel_time_between(
                previous_location,
                task.location_id,
                engineer.vehicle_type,
            )
            arrival_time = current_time + travel_time
            service_start = max(arrival_time, hhmm_to_minutes(task.window_start))
            service_end = service_start + problem.service_duration(task)
            if service_start > hhmm_to_minutes(task.window_end):
                return None
            if service_end > hhmm_to_minutes(availability.available_until):
                return None
            distance = problem.travel_distance_between(
                previous_location,
                task.location_id,
                engineer.vehicle_type,
            )
            schedule.append(
                _ScheduledStop(
                    task=task,
                    arrival_time=arrival_time,
                    service_start_time=service_start,
                    service_end_time=service_end,
                    distance_from_previous_km=distance,
                )
            )
            current_time = service_end
            previous_location = task.location_id
        return schedule

    @staticmethod
    def _resources_are_available(
        problem: OptimizationProblem,
        engineer: Engineer,
        task: Task,
        service_start: int,
        service_end: int,
        resource_intervals: dict[str, list[tuple[str, int, int]]],
    ) -> bool:
        """Проверяет конфликт сервисного интервала с другими инженерами."""
        if service_start == service_end:
            return True
        for resource_id in resource_ids_used_for_task(problem, engineer, task):
            for other_engineer_id, other_start, other_end in resource_intervals.get(
                resource_id, ()
            ):
                if other_engineer_id != engineer.id and service_start < other_end and other_start < service_end:
                    return False
        return True

    @staticmethod
    def _unassigned_reason(
        problem: OptimizationProblem,
        task: Task,
        availability_by_engineer: dict[str, EngineerAvailability],
    ) -> UnassignedReason:
        """Определяет основную причину, по которой заявка не назначена."""
        if not any(
            task.required_skills.issubset(engineer.qualifications)
            for engineer in problem.engineers
        ):
            return UnassignedReason(
                UnassignedReasonCode.MISSING_QUALIFICATION,
                "Нет инженера с требуемым навыком.",
            )
        if not any(
            task.required_skills.issubset(engineer.qualifications)
            and engineer_has_required_equipment(problem, engineer, task)
            for engineer in problem.engineers
        ):
            return UnassignedReason(
                UnassignedReasonCode.MISSING_EQUIPMENT,
                "У подходящих инженеров нет требуемого оборудования.",
            )
        if not any(
            engineer_can_execute_task(problem, engineer, task)
            for engineer in problem.engineers
        ):
            return UnassignedReason(
                UnassignedReasonCode.MISSING_VEHICLE_TYPE,
                "У подходящих инженеров нет требуемого типа транспорта.",
            )
        can_start_in_window = False
        can_complete_single_task = False
        for engineer in problem.engineers:
            if not engineer_can_execute_task(problem, engineer, task):
                continue
            availability = availability_by_engineer[engineer.id]
            arrival_time = hhmm_to_minutes(availability.available_from) + problem.travel_time_between(
                engineer.start_location_id,
                task.location_id,
                engineer.vehicle_type,
            )
            service_start = max(arrival_time, hhmm_to_minutes(task.window_start))
            if service_start > hhmm_to_minutes(task.window_end):
                continue
            can_start_in_window = True
            if service_start + task.duration_minutes <= hhmm_to_minutes(
                availability.available_until
            ):
                can_complete_single_task = True
        if not can_start_in_window:
            return UnassignedReason(
                UnassignedReasonCode.IMPOSSIBLE_TIME_WINDOW,
                "Ни один инженер не может начать заявку в её окне.",
            )
        return UnassignedReason(
            UnassignedReasonCode.OUTSIDE_WORKING_HOURS,
            "Заявка не поместилась в маршрут с уже назначенными работами."
            if can_complete_single_task
            else "Работа не помещается в доступную смену.",
        )

    @staticmethod
    def _build_route(
        engineer: Engineer,
        schedule: list[_ScheduledStop],
        problem: OptimizationProblem,
    ) -> EngineerRoute:
        """Преобразует последовательное расписание в доменный маршрут."""
        previous_location = problem.route_start_location(engineer)
        total_travel = 0
        total_distance = 0.0
        total_service = 0
        stops: list[RouteStop] = []
        for scheduled_stop in schedule:
            task = scheduled_stop.task
            travel_time = problem.travel_time_between(
                previous_location,
                task.location_id,
                engineer.vehicle_type,
            )
            stops.append(
                RouteStop(
                    task_id=task.id,
                    arrival_time=minutes_to_hhmm(scheduled_stop.arrival_time),
                    service_start_time=minutes_to_hhmm(
                        scheduled_stop.service_start_time
                    ),
                    service_end_time=minutes_to_hhmm(
                        scheduled_stop.service_end_time
                    ),
                    travel_time_from_previous=travel_time,
                    distance_from_previous_km=scheduled_stop.distance_from_previous_km,
                )
            )
            total_travel += travel_time
            total_distance += scheduled_stop.distance_from_previous_km
            total_service += problem.service_duration(task)
            previous_location = task.location_id
        return EngineerRoute(
            engineer_id=engineer.id,
            stops=tuple(stops),
            total_travel_minutes=total_travel,
            total_service_minutes=total_service,
            total_distance_km=total_distance,
        )
