"""Экспериментальный VRPTW solver на основе ICO/DE и random keys."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np

from .baseline_optimizer import GreedyBaselineOptimizer
from .config import ICORoutingConfig, OptimizerConfig
from .constraints import (
    engineer_can_execute_task,
    engineer_has_required_equipment,
    resource_ids_used_for_task,
)
from .ico_de import CountriesAlgorithm, ICOConfig
from .interfaces import RouteOptimizer
from .models import (
    Engineer,
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
class _DecodedStop:
    """Одна допустимая остановка, полученная при декодировании random keys."""

    task: Task
    arrival: int
    service_start: int
    service_end: int
    travel_minutes: int
    distance_km: float


@dataclass(frozen=True, slots=True)
class _DecodedCandidate:
    """Полностью декодированный план и его компоненты objective."""

    routes: tuple[tuple[_DecodedStop, ...], ...]
    unassigned_task_indexes: frozenset[int]
    unassigned_penalty: int
    used_engineers_penalty: int
    distance_penalty: int
    travel_time_penalty: int

    @property
    def total_objective(self) -> int:
        """Возвращает сумму мягких компонентов; hard constraints уже соблюдены."""
        return (
            self.unassigned_penalty
            + self.used_engineers_penalty
            + self.distance_penalty
            + self.travel_time_penalty
        )


class _RandomKeysVRPTW:
    """Кодирует назначение и порядок заявок вещественным вектором ``[0, 1]``.

    Для каждой из ``J`` заявок используются две координаты:

    * ``x[j]`` попадает в одну из ``E + 1`` равных корзин: нулевая означает
      «не назначать», остальные выбирают инженера;
    * ``x[J + j]`` — random key порядка. Заявки одного инженера сортируются
      по этому ключу и затем последовательно вставляются в расписание.

    Недопустимая по hard constraints вставка пропускается. Поэтому objective
    всегда оценивает допустимый план, а нарушение ограничения превращается в
    неназначенную заявку с настроенным штрафом.
    """

    def __init__(self, problem: OptimizationProblem, config: OptimizerConfig) -> None:
        """Подготавливает индексы, смены и неизменяемые назначения."""
        self.problem = problem
        self.config = config
        self.tasks = problem.planning_tasks
        self.engineers = problem.engineers
        self.task_count = len(self.tasks)
        self.engineer_count = len(self.engineers)
        self.dimension = 2 * self.task_count
        self.engineer_index = {
            engineer.id: index for index, engineer in enumerate(self.engineers)
        }
        self.availability_by_engineer = {
            availability.engineer_id: availability
            for availability in problem.availabilities
        }
        self.fixed_engineer_index = {
            task_id: self.engineer_index[engineer_id]
            for task_id, engineer_id in problem.fixed_task_engineer_by_id.items()
        }

    def objective(self, vector: np.ndarray) -> float:
        """Возвращает декомпозированную стоимость декодированного плана."""
        return float(self.decode(vector).total_objective)

    def split(self, vector: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
        """Преобразует первую половину в корзины инженеров и читает ключи порядка."""
        values = np.asarray(vector, dtype=float)
        if values.shape != (self.dimension,) or not np.all(np.isfinite(values)):
            raise ValueError(f"Ожидается конечный vector формы ({self.dimension},)")
        values = np.clip(values, 0.0, 1.0)
        assignment = np.floor(
            values[: self.task_count] * (self.engineer_count + 1)
        ).astype(np.int32)
        np.minimum(assignment, self.engineer_count, out=assignment)
        return assignment, values[self.task_count :]

    def encode_result(self, result: OptimizationResult) -> np.ndarray:
        """Кодирует допустимый baseline как начальную точку ICO."""
        vector = np.zeros(self.dimension, dtype=float)
        task_index = {task.id: index for index, task in enumerate(self.tasks)}
        # Центр нулевой корзины избегает пограничной неоднозначности.
        vector[: self.task_count] = 0.5 / (self.engineer_count + 1)
        for engineer_index, engineer in enumerate(self.engineers):
            route = result.routes[engineer.id]
            for rank, stop in enumerate(route.stops, start=1):
                index = task_index[stop.task_id]
                code = engineer_index + 1
                vector[index] = (code + 0.5) / (self.engineer_count + 1)
                vector[self.task_count + index] = rank / (len(route.stops) + 1)
        return vector

    def decode(self, vector: Sequence[float]) -> _DecodedCandidate:
        """Строит расписание, последовательно принимая только допустимые вставки."""
        assignment, order_keys = self.split(vector)
        routes: list[list[_DecodedStop]] = [
            [] for _ in range(self.engineer_count)
        ]
        unassigned = set(range(self.task_count))
        resource_intervals: dict[str, list[tuple[str, int, int]]] = {}
        routers_used = [0] * self.engineer_count

        for engineer_index, engineer in enumerate(self.engineers):
            candidate_indexes = [
                index
                for index, task in enumerate(self.tasks)
                if self._assigned_engineer(index, task, assignment) == engineer_index
            ]
            # Начатая заявка обязана быть первым активным визитом. Остальные
            # заявки сортируются исключительно по random key хромосомы.
            candidate_indexes.sort(
                key=lambda index: (
                    0 if self.tasks[index].status in {TaskStatus.EN_ROUTE, TaskStatus.IN_PROGRESS}
                    and self.tasks[index].id in self.fixed_engineer_index else 1,
                    float(order_keys[index]),
                    index,
                )
            )
            availability = self.availability_by_engineer[engineer.id]
            current_time = self.problem.route_start_minutes(availability)
            previous_location = self.problem.route_start_location(engineer)

            for task_index in candidate_indexes:
                task = self.tasks[task_index]
                if not engineer_can_execute_task(self.problem, engineer, task):
                    continue
                if (
                    self.problem.consider_equipment
                    and routers_used[engineer_index] + task.required_router_count
                    > self.problem.available_router_count_for_planning(engineer)
                ):
                    continue
                travel = self.problem.travel_time_between(
                    previous_location, task.location_id, engineer.vehicle_type
                )
                arrival = current_time + travel
                service_start = max(arrival, hhmm_to_minutes(task.window_start))
                service_end = service_start + self.problem.service_duration(task)
                if service_start > hhmm_to_minutes(task.window_end):
                    continue
                if service_end > hhmm_to_minutes(availability.available_until):
                    continue
                if not self._resources_available(
                    engineer, task, service_start, service_end, resource_intervals
                ):
                    continue
                distance = self.problem.travel_distance_between(
                    previous_location, task.location_id, engineer.vehicle_type
                )
                routes[engineer_index].append(
                    _DecodedStop(
                        task=task,
                        arrival=arrival,
                        service_start=service_start,
                        service_end=service_end,
                        travel_minutes=travel,
                        distance_km=distance,
                    )
                )
                for resource_id in resource_ids_used_for_task(
                    self.problem, engineer, task
                ):
                    resource_intervals.setdefault(resource_id, []).append(
                        (engineer.id, service_start, service_end)
                    )
                unassigned.discard(task_index)
                routers_used[engineer_index] += task.required_router_count
                current_time = service_end
                previous_location = task.location_id

        total_distance = math.fsum(
            stop.distance_km for route in routes for stop in route
        )
        total_travel = sum(
            stop.travel_minutes for route in routes for stop in route
        )
        unassigned_penalty = sum(
            self.config.unassigned_penalty
            * self.config.unassigned_multiplier(self.tasks[index])
            for index in unassigned
        )
        return _DecodedCandidate(
            routes=tuple(tuple(route) for route in routes),
            unassigned_task_indexes=frozenset(unassigned),
            unassigned_penalty=unassigned_penalty,
            used_engineers_penalty=(
                sum(bool(route) for route in routes)
                * self.config.used_engineers_penalty
            ),
            distance_penalty=int(round(
                total_distance * self.config.distance_penalty_per_km
            )),
            travel_time_penalty=(
                total_travel * self.config.travel_time_penalty_per_minute
            ),
        )

    def _assigned_engineer(
        self, task_index: int, task: Task, assignment: np.ndarray
    ) -> int | None:
        """Возвращает назначенного инженера с приоритетом жёсткой фиксации."""
        if task.id in self.fixed_engineer_index:
            return self.fixed_engineer_index[task.id]
        code = int(assignment[task_index])
        return None if code == 0 else code - 1

    def _resources_available(
        self,
        engineer: Engineer,
        task: Task,
        service_start: int,
        service_end: int,
        resource_intervals: dict[str, list[tuple[str, int, int]]],
    ) -> bool:
        """Запрещает одновременное использование одного экземпляра ресурса."""
        if service_start == service_end:
            return True
        for resource_id in resource_ids_used_for_task(
            self.problem, engineer, task
        ):
            for other_engineer, other_start, other_end in resource_intervals.get(
                resource_id, ()
            ):
                if (
                    other_engineer != engineer.id
                    and service_start < other_end
                    and other_start < service_end
                ):
                    return False
        return True


class ICOOptimizer(RouteOptimizer):
    """Строит VRPTW-маршруты метаэвристикой ICO/DE с random keys."""

    def __init__(
        self,
        config: OptimizerConfig | None = None,
        ico_config: ICORoutingConfig | None = None,
    ) -> None:
        """Создаёт solver с общими весами и отдельными параметрами поиска."""
        self.config = config or OptimizerConfig()
        self.ico_config = ico_config or ICORoutingConfig()

    def optimize(self, problem: OptimizationProblem) -> OptimizationResult:
        """Запускает ICO от жадного допустимого плана и возвращает лучший маршрут."""
        codec = _RandomKeysVRPTW(problem, self.config)
        baseline = GreedyBaselineOptimizer(self.config).optimize(problem)
        initial_vector = codec.encode_result(baseline)
        if codec.dimension == 0:
            return baseline
        continuous_config = ICOConfig(
            x_min=[0.0] * codec.dimension,
            x_max=[1.0] * codec.dimension,
            countries_count=self.ico_config.countries_count,
            country_population=self.ico_config.country_population,
            maximum_iterations=self.ico_config.maximum_iterations,
            gray_country_fraction=self.ico_config.gray_country_fraction,
            initial_x=initial_vector,
            random_seed=self.ico_config.random_seed,
            printing=self.ico_config.printing,
        )
        search_result = CountriesAlgorithm(
            codec.objective, continuous_config
        ).start(max_calls=self.ico_config.maximum_function_evaluations)
        candidate = codec.decode(search_result.x)
        result = self._build_result(problem, codec, candidate)
        # Из-за ограниченного бюджета метаэвристика не должна ухудшать
        # гарантированно допустимую стартовую точку.
        return result if result.total_objective <= baseline.total_objective else baseline

    def _build_result(
        self,
        problem: OptimizationProblem,
        codec: _RandomKeysVRPTW,
        candidate: _DecodedCandidate,
    ) -> OptimizationResult:
        """Преобразует внутреннее расписание ICO в общий domain-результат."""
        routes: dict[str, EngineerRoute] = {}
        for engineer_index, engineer in enumerate(problem.engineers):
            decoded_route = candidate.routes[engineer_index]
            stops = tuple(
                RouteStop(
                    task_id=stop.task.id,
                    arrival_time=minutes_to_hhmm(stop.arrival),
                    service_start_time=minutes_to_hhmm(stop.service_start),
                    service_end_time=minutes_to_hhmm(stop.service_end),
                    travel_time_from_previous=stop.travel_minutes,
                    distance_from_previous_km=stop.distance_km,
                )
                for stop in decoded_route
            )
            routes[engineer.id] = EngineerRoute(
                engineer_id=engineer.id,
                stops=stops,
                total_travel_minutes=sum(stop.travel_minutes for stop in decoded_route),
                total_service_minutes=sum(
                    problem.service_duration(stop.task) for stop in decoded_route
                ),
                total_distance_km=math.fsum(
                    stop.distance_km for stop in decoded_route
                ),
            )
        unassigned_task_ids = tuple(
            codec.tasks[index].id
            for index in range(codec.task_count)
            if index in candidate.unassigned_task_indexes
        )
        unassigned_reasons = {
            codec.tasks[index].id: self._unassigned_reason(problem, codec.tasks[index])
            for index in candidate.unassigned_task_indexes
        }
        distance_by_engineer = {
            engineer_id: route.total_distance_km
            for engineer_id, route in routes.items()
        }
        travel_time_by_engineer = {
            engineer_id: route.total_travel_minutes
            for engineer_id, route in routes.items()
        }
        return OptimizationResult(
            routes=routes,
            unassigned_task_ids=unassigned_task_ids,
            unassigned_reasons=unassigned_reasons,
            distance_by_engineer=distance_by_engineer,
            total_distance=math.fsum(distance_by_engineer.values()),
            travel_time_by_engineer=travel_time_by_engineer,
            total_travel_time=sum(travel_time_by_engineer.values()),
            used_engineers_count=sum(bool(route.stops) for route in routes.values()),
            assigned_task_count=sum(len(route.stops) for route in routes.values()),
            unassigned_task_count=len(unassigned_task_ids),
            total_objective=candidate.total_objective,
            total_service_minutes=sum(route.total_service_minutes for route in routes.values()),
            unassigned_penalty=candidate.unassigned_penalty,
            used_engineers_penalty=candidate.used_engineers_penalty,
            distance_penalty=candidate.distance_penalty,
            travel_time_penalty=candidate.travel_time_penalty,
        )

    @staticmethod
    def _unassigned_reason(
        problem: OptimizationProblem, task: Task
    ) -> UnassignedReason:
        """Формирует ту же структурированную причину, что остальные solver’ы."""
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
        availability_by_engineer = {
            availability.engineer_id: availability
            for availability in problem.availabilities
        }
        can_start_in_window = False
        can_finish_in_shift = False
        for engineer in problem.engineers:
            if not engineer_can_execute_task(problem, engineer, task):
                continue
            availability = availability_by_engineer[engineer.id]
            arrival = (
                problem.route_start_minutes(availability)
                + problem.travel_time_between(
                    problem.route_start_location(engineer),
                    task.location_id,
                    engineer.vehicle_type,
                )
            )
            service_start = max(arrival, hhmm_to_minutes(task.window_start))
            if service_start > hhmm_to_minutes(task.window_end):
                continue
            can_start_in_window = True
            if (
                service_start + problem.service_duration(task)
                <= hhmm_to_minutes(availability.available_until)
            ):
                can_finish_in_shift = True
        if not can_start_in_window:
            return UnassignedReason(
                UnassignedReasonCode.IMPOSSIBLE_TIME_WINDOW,
                "Ни один инженер не может начать заявку в её временном окне.",
            )
        return UnassignedReason(
            UnassignedReasonCode.OUTSIDE_WORKING_HOURS,
            "Заявка не поместилась в маршрут с другими работами."
            if can_finish_in_shift
            else "Работа не помещается в доступную смену.",
        )
