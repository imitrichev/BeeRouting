"""Альтернативный solver на базе Timefold.

Модуль намеренно использует текущие domain-модели проекта. Timefold получает
только внутреннюю планировочную оболочку: ``OptimizationProblem`` остаётся
источником всех ограничений и матриц, а наружу возвращается тот же
``OptimizationResult``, что и у OR-Tools.

Зависимость импортируется лениво. Благодаря этому основной OR-Tools solver и
тесты доменной модели продолжают работать без установленного JDK.
"""

from dataclasses import dataclass, field
import importlib
import math
from typing import Any, Annotated, Iterable

from .config import OptimizerConfig
from .constraints import engineer_can_execute_task, resource_ids_used_for_task
from .interfaces import RouteOptimizer
from .models import (
    Engineer,
    EngineerAvailability,
    EngineerRoute,
    OptimizationProblem,
    OptimizationResult,
    RouteStop,
    Task,
    UnassignedReason,
    UnassignedReasonCode,
    VehicleType,
    hhmm_to_minutes,
    minutes_to_hhmm,
)
from .ortools_optimizer import ORToolsOptimizer


class TimefoldUnavailableError(RuntimeError):
    """Timefold нельзя запустить в текущем окружении."""


@dataclass(frozen=True, slots=True)
class _ScheduledStop:
    """Промежуточная остановка с числовым временем в минутах."""

    task: Task
    arrival_time: int
    service_start_time: int
    service_end_time: int
    distance_from_previous_km: float


@dataclass(frozen=True, slots=True)
class _TimefoldApi:
    """Небольшой контейнер импортированных классов Timefold."""

    SolverFactory: Any
    Duration: Any
    ScoreDirectorFactoryConfig: Any
    SolverConfig: Any
    TerminationConfig: Any
    PlanningEntityCollectionProperty: Any
    PlanningId: Any
    PlanningListVariable: Any
    PlanningScore: Any
    ProblemFactCollectionProperty: Any
    ValueRangeProvider: Any
    planning_entity: Any
    planning_solution: Any
    Constraint: Any
    ConstraintFactory: Any
    HardMediumSoftScore: Any
    constraint_provider: Any


def _load_timefold_api() -> _TimefoldApi:
    """Лениво загружает установленный Python API Timefold.

    Импорт выполняется только при фактическом запуске Timefold, поэтому
    основной OR-Tools solver не требует JVM. Корневой справочный файл команды
    переименован и больше не затеняет установленный пакет ``timefold``.
    """

    try:
        solver = importlib.import_module("timefold.solver")
        config = importlib.import_module("timefold.solver.config")
        domain = importlib.import_module("timefold.solver.domain")
        score = importlib.import_module("timefold.solver.score")
    except Exception as exc:
        raise TimefoldUnavailableError(
            "Timefold не готов к запуску. Установите зависимости ядра и JDK 17+: "
            "pip install -r backend/optimization/requirements.txt"
        ) from exc

    return _TimefoldApi(
        SolverFactory=solver.SolverFactory,
        Duration=config.Duration,
        ScoreDirectorFactoryConfig=config.ScoreDirectorFactoryConfig,
        SolverConfig=config.SolverConfig,
        TerminationConfig=config.TerminationConfig,
        PlanningEntityCollectionProperty=domain.PlanningEntityCollectionProperty,
        PlanningId=domain.PlanningId,
        PlanningListVariable=domain.PlanningListVariable,
        PlanningScore=domain.PlanningScore,
        ProblemFactCollectionProperty=domain.ProblemFactCollectionProperty,
        ValueRangeProvider=domain.ValueRangeProvider,
        planning_entity=domain.planning_entity,
        planning_solution=domain.planning_solution,
        Constraint=score.Constraint,
        ConstraintFactory=score.ConstraintFactory,
        HardMediumSoftScore=score.HardMediumSoftScore,
        constraint_provider=score.constraint_provider,
    )


def _build_timefold_model(
    api: _TimefoldApi,
    config: OptimizerConfig,
    include_resource_constraints: bool = True,
) -> tuple[Any, Any, Any, Any]:
    """Создаёт внутренние Timefold-классы для одного запуска.

    Классы создаются динамически, потому что импорт Timefold необязателен для
    OR-Tools. Планировочная сущность содержит только порядок заявок инженера;
    навыки, оборудование и транспорт берутся из текущего ``OptimizationProblem``.
    """

    @dataclass
    class PlanningTask:
        """Значение списка Timefold, ссылающееся на domain Task."""

        # PlanningId нужен Timefold для однозначного сопоставления planning
        # value при переносе заявки между списками и при клонировании решения.
        # Старый timef_solver.py это поле имел; в текущем адаптере его не было.
        task_id: Annotated[str, api.PlanningId]
        location_id: str
        window_start_minutes: int
        window_end_minutes: int
        duration_minutes: int
        priority_multiplier: int
        task: Task

        def __hash__(self) -> int:
            """Даёт Timefold стабильный ключ planning value при клонировании."""
            return hash(self.task_id)

        def __eq__(self, other: object) -> bool:
            """Считает две planning value одной заявкой по её идентификатору."""
            return isinstance(other, PlanningTask) and self.task_id == other.task_id

    @api.planning_entity
    @dataclass
    class PlanningEngineer:
        """Маршрут инженера как изменяемый список заявок Timefold."""

        engineer_id: Annotated[str, api.PlanningId]
        engineer: Engineer
        availability: EngineerAvailability
        available_from_minutes: int
        available_until_minutes: int
        compatible_task_ids: list[str]
        travel_time_matrix: dict[str, dict[str, int]]
        travel_distance_matrix: dict[str, dict[str, float]]
        resource_ids_by_task: dict[str, list[str]]
        tasks: Annotated[list[PlanningTask], api.PlanningListVariable(allows_unassigned_values=True)] = field(default_factory=list)

        def domain_tasks(self) -> list[Task]:
            """Возвращает заявки в порядке, выбранном Timefold."""

            return [item.task for item in self.tasks]

        def compatible_count(self) -> int:
            """Считает заявки, нарушающие skill/equipment/vehicle constraint.

            ``compatible_task_ids`` рассчитывается до запуска JVM. Внутри
            constraint stream остаётся только проверка идентификатора; это
            позволяет Timefold перевести функцию без вызова Python-кода из
            соседнего модуля.
            """

            violations = 0
            for item in self.tasks:
                if item.task_id not in self.compatible_task_ids:
                    violations += 1
            return violations

        def time_violation_count(self) -> int:
            """Возвращает единицу за нарушение окна или смены.

            Время считается последовательно: после прибытия инженер может
            ждать начала окна, затем выполняет работу и продолжает с её
            окончания. Возврат на базу не добавляется.
            """

            current_time = self.available_from_minutes
            previous_location = self.engineer.start_location_id
            for item in self.tasks:
                travel_time = self.travel_time_matrix[previous_location][item.location_id]
                arrival_time = current_time + travel_time
                service_start = max(arrival_time, item.window_start_minutes)
                service_end = service_start + item.duration_minutes
                if service_start > item.window_end_minutes or service_end > self.available_until_minutes:
                    return 1
                current_time = service_end
                previous_location = item.location_id
            return 0

        def route_distance(self) -> float:
            """Считает расстояние маршрута в километрах без возврата на базу."""

            total_distance = 0.0
            previous_location = self.engineer.start_location_id
            for item in self.tasks:
                total_distance += self.travel_distance_matrix[previous_location][item.location_id]
                previous_location = item.location_id
            return total_distance

        def route_travel_time(self) -> int:
            """Считает суммарное время движения маршрута в минутах."""

            total_time = 0
            previous_location = self.engineer.start_location_id
            for item in self.tasks:
                total_time += self.travel_time_matrix[previous_location][item.location_id]
                previous_location = item.location_id
            return total_time

        def resource_conflict_count(self, other) -> int:
            """Считает пересечения общих экземпляров ресурсов двух маршрутов."""

            if self.time_violation_count() > 0 or other.time_violation_count() > 0:
                return 0
            left_intervals: dict[str, list[tuple[int, int]]] = {}
            right_intervals: dict[str, list[tuple[int, int]]] = {}
            current_time = self.available_from_minutes
            previous_location = self.engineer.start_location_id
            for item in self.tasks:
                arrival_time = current_time + self.travel_time_matrix[previous_location][item.location_id]
                service_start = max(arrival_time, item.window_start_minutes)
                service_end = service_start + item.duration_minutes
                for resource_id in self.resource_ids_by_task.get(item.task_id, []):
                    left_intervals.setdefault(resource_id, []).append((service_start, service_end))
                current_time = service_end
                previous_location = item.location_id
            current_time = other.available_from_minutes
            previous_location = other.engineer.start_location_id
            for item in other.tasks:
                arrival_time = current_time + other.travel_time_matrix[previous_location][item.location_id]
                service_start = max(arrival_time, item.window_start_minutes)
                service_end = service_start + item.duration_minutes
                for resource_id in other.resource_ids_by_task.get(item.task_id, []):
                    right_intervals.setdefault(resource_id, []).append((service_start, service_end))
                current_time = service_end
                previous_location = item.location_id
            conflicts = 0
            for resource_id in left_intervals.keys() & right_intervals.keys():
                for left_start, left_end in left_intervals[resource_id]:
                    for right_start, right_end in right_intervals[resource_id]:
                        if left_start < right_end and right_start < left_end:
                            conflicts += 1
            return conflicts

    @api.planning_solution
    @dataclass
    class PlanningSolution:
        """План Timefold с инженерами и полным диапазоном заявок."""

        engineers: Annotated[list[PlanningEngineer], api.PlanningEntityCollectionProperty]
        tasks: Annotated[list[PlanningTask], api.ProblemFactCollectionProperty, api.ValueRangeProvider]
        score: Annotated[api.HardMediumSoftScore | None, api.PlanningScore] = None

    def constraints(factory: Any) -> list[Any]:
        """Описывает hard constraints и компоненты objective Timefold."""

        hard_score = api.HardMediumSoftScore.ONE_HARD
        medium_score = api.HardMediumSoftScore.ONE_MEDIUM
        soft_score = api.HardMediumSoftScore.ONE_SOFT

        # Несовместимые назначения и нарушение расписания всегда находятся
        # в hard-части score и поэтому не могут быть выгодно компенсированы
        # пробегом или числом инженеров.
        constraints_list = [
            factory.for_each(PlanningEngineer)
            .filter(lambda engineer: engineer.compatible_count() > 0)
            .penalize(hard_score, lambda engineer: engineer.compatible_count())
            .as_constraint("Hard resource compatibility"),
            factory.for_each(PlanningEngineer)
            .filter(lambda engineer: engineer.time_violation_count() > 0)
            .penalize(hard_score, lambda engineer: engineer.time_violation_count())
            .as_constraint("Hard windows and shift"),
            # За назначенную заявку даём reward. Так неназначение эквивалентно
            # текущему штрафу: постоянная сумма всех возможных заявок не меняет
            # порядок планов, а срочная заявка получает вес из OptimizerConfig.
            factory.for_each(PlanningEngineer)
            .filter(lambda engineer: len(engineer.tasks) > 0)
            .reward(
                medium_score,
                lambda engineer: sum(
                    config.unassigned_penalty * item.priority_multiplier
                    for item in engineer.tasks
                ),
            )
            .as_constraint("Assigned task priority"),
            factory.for_each(PlanningEngineer)
            .filter(lambda engineer: len(engineer.tasks) > 0)
            .penalize(soft_score, lambda engineer: config.used_engineers_penalty)
            .as_constraint("Used engineers"),
            factory.for_each(PlanningEngineer)
            .filter(lambda engineer: len(engineer.tasks) > 0)
            .penalize(
                soft_score,
                lambda engineer: int(
                    round(
                        engineer.route_distance()
                        * config.distance_penalty_per_km
                    )
                ),
            )
            .as_constraint("Route distance"),
            factory.for_each(PlanningEngineer)
            .filter(lambda engineer: len(engineer.tasks) > 0)
            .penalize(
                soft_score,
                lambda engineer: engineer.route_travel_time()
                * config.travel_time_penalty_per_minute,
            )
            .as_constraint("Travel time"),
        ]

        # Расширенная resource-модель проекта сохраняется: один экземпляр
        # оборудования или транспорта нельзя занять одновременно в двух
        # маршрутах. Простое available_equipment по-прежнему не создаёт
        # искусственного конфликта.
        if include_resource_constraints:
            resource_constraint = (
                factory.for_each(PlanningEngineer)
                .join(PlanningEngineer)
                .filter(
                    lambda left, right: left.engineer_id < right.engineer_id
                    and left.resource_conflict_count(right) > 0
                )
                .penalize(
                    hard_score,
                    lambda left, right: left.resource_conflict_count(right),
                )
                .as_constraint("Shared resource overlap")
            )
            constraints_list.append(resource_constraint)
        return constraints_list

    decorated_constraints = api.constraint_provider(constraints)
    return PlanningTask, PlanningEngineer, PlanningSolution, decorated_constraints


class TimefoldOptimizer(RouteOptimizer):
    """Отдельный solver Timefold с тем же входом и выходом, что у OR-Tools.

    Timefold меняет распределение и порядок заявок через planning list
    variable. Он не получает OSRM и не строит матрицы самостоятельно: все
    travel time, distance и vehicle-specific профили читаются из
    ``OptimizationProblem``.
    """

    DEFAULT_TIME_LIMIT_SECONDS = 20  # Лимит поиска Timefold по умолчанию, секунды.

    def __init__(
        self,
        config: OptimizerConfig | None = None,
        *,
        time_limit_seconds: int | None = None,
    ) -> None:
        """Создаёт solver и необязательный короткий лимит для benchmark/test."""

        self.config = config or OptimizerConfig()
        self.time_limit_seconds = (
            self.DEFAULT_TIME_LIMIT_SECONDS
            if time_limit_seconds is None
            else time_limit_seconds
        )
        if self.time_limit_seconds <= 0:
            raise ValueError("time_limit_seconds должен быть положительным")

    def optimize(self, problem: OptimizationProblem) -> OptimizationResult:
        """Запускает Timefold и преобразует его план в domain-результат."""

        api = _load_timefold_api()
        try:
            has_limited_resources = any(
                resource_ids_used_for_task(problem, engineer, task)
                for engineer in problem.engineers
                for task in problem.tasks
            )
            PlanningTask, PlanningEngineer, PlanningSolution, constraints = _build_timefold_model(
                api,
                self.config,
                include_resource_constraints=has_limited_resources,
            )
        except Exception as exc:
            raise TimefoldUnavailableError(
                "Timefold не запустился. Проверьте установку timefold и JDK 17+ "
                "с доступной переменной JAVA_HOME."
            ) from exc
        availability_by_engineer = {
            item.engineer_id: item for item in problem.availabilities
        }
        planning_tasks = [
            PlanningTask(
                task_id=task.id,
                location_id=task.location_id,
                window_start_minutes=hhmm_to_minutes(task.window_start),
                window_end_minutes=hhmm_to_minutes(task.window_end),
                duration_minutes=task.duration_minutes,
                priority_multiplier=(
                    self.config.urgent_unassigned_multiplier
                    if task.priority.value == "URGENT"
                    else self.config.normal_unassigned_multiplier
                ),
                task=task,
            )
            for task in problem.tasks
        ]
        entities = [
            PlanningEngineer(
                engineer_id=engineer.id,
                engineer=engineer,
                availability=availability_by_engineer[engineer.id],
                available_from_minutes=hhmm_to_minutes(
                    availability_by_engineer[engineer.id].available_from
                ),
                available_until_minutes=hhmm_to_minutes(
                    availability_by_engineer[engineer.id].available_until
                ),
                compatible_task_ids=[
                    task.id
                    for task in problem.tasks
                    if engineer_can_execute_task(problem, engineer, task)
                ],
                travel_time_matrix={
                    source: dict(destinations)
                    for source, destinations in (
                        problem.travel_time_matrices_by_vehicle.get(
                            engineer.vehicle_type, problem.travel_time_matrix
                        )
                    ).items()
                },
                travel_distance_matrix={
                    source: dict(destinations)
                    for source, destinations in (
                        problem.travel_distance_matrices_by_vehicle.get(
                            engineer.vehicle_type, problem.travel_distance_matrix
                        )
                    ).items()
                },
                resource_ids_by_task={
                    task.id: list(resource_ids_used_for_task(problem, engineer, task))
                    for task in problem.tasks
                },
            )
            for engineer in problem.engineers
        ]
        planning_task_by_id = {
            planning_task.task.id: planning_task for planning_task in planning_tasks
        }
        entity_by_id = {entity.engineer_id: entity for entity in entities}
        self._build_initial_solution(problem, entities, planning_task_by_id)
        initial_solution = PlanningSolution(entities, planning_tasks)

        # Входной план уже заполнен допустимыми маршрутами. Timefold запускает
        # свою стандартную construction heuristic и сразу завершает её с
        # step count (0), что является нормальным для полностью инициализиро-
        # ванного planning list variable. После этого штатный Local Search
        # использует list moves так же, как в проверенном старом timef_solver.py.
        # Late Acceptance позволяет принять временно худший допустимый ход и
        # выйти из локального минимума, когда объединение маршрутов требует
        # нескольких последовательных перестановок.
        solver_xml = """
        <solver xmlns="https://timefold.ai/xsd/solver">
          <localSearch>
            <acceptor>
              <lateAcceptanceSize>200</lateAcceptanceSize>
            </acceptor>
          </localSearch>
        </solver>
        """
        solver_config = api.SolverConfig(
            solution_class=PlanningSolution,
            entity_class_list=[PlanningEngineer],
            xml_source_text=solver_xml,
            score_director_factory_config=api.ScoreDirectorFactoryConfig(
                constraint_provider_function=constraints
            ),
            termination_config=api.TerminationConfig(
                spent_limit=api.Duration(seconds=self.time_limit_seconds)
            ),
        )
        try:
            solver = api.SolverFactory.create(solver_config).build_solver()
            solved = solver.solve(initial_solution)
        except Exception as exc:  # Timefold wraps missing JDK/JVM errors.
            raise TimefoldUnavailableError(
                "Timefold не запустился. Проверьте установку timefold и JDK 17+ "
                "с доступной переменной JAVA_HOME."
            ) from exc
        return self._build_result(problem, solved)

    @staticmethod
    def _build_initial_solution(
        problem: OptimizationProblem,
        entities: list[Any],
        planning_task_by_id: dict[str, Any],
    ) -> None:
        """Строит допустимый warm start по стратегии старого Timefold solver.

        Заявки сначала идут по приоритету и началу окна. Для каждой заявки
        выбирается маршрут с наименьшим числом остановок, затем — с меньшим
        пробегом. Это только стартовая точка поиска; явные list move selectors
        после этого могут менять и исполнителя, и порядок.
        """
        resource_intervals: dict[str, list[tuple[str, int, int]]] = {}
        for task in sorted(
            problem.tasks,
            key=lambda item: (
                item.priority.value != "URGENT",
                hhmm_to_minutes(item.window_start),
                hhmm_to_minutes(item.window_end),
                item.id,
            ),
        ):
            candidates: list[tuple[int, float, str, Any, _ScheduledStop]] = []
            for entity in entities:
                if task.id not in entity.compatible_task_ids:
                    continue
                current_tasks = [item.task for item in entity.tasks]
                schedule = _schedule_tasks(
                    problem,
                    entity.engineer,
                    entity.availability,
                    current_tasks + [task],
                )
                if schedule is None:
                    continue
                candidate_stop = schedule[-1]
                if not _resources_are_available(
                    problem,
                    entity.engineer,
                    task,
                    candidate_stop,
                    resource_intervals,
                ):
                    continue
                distance = math.fsum(stop.distance_from_previous_km for stop in schedule)
                candidates.append(
                    (len(entity.tasks), distance, entity.engineer_id, entity, candidate_stop)
                )
            if not candidates:
                continue
            _, _, _, selected_entity, selected_stop = min(
                candidates, key=lambda value: value[:3]
            )
            selected_entity.tasks.append(planning_task_by_id[task.id])
            for resource_id in resource_ids_used_for_task(
                problem, selected_entity.engineer, task
            ):
                resource_intervals.setdefault(resource_id, []).append(
                    (
                        selected_entity.engineer.id,
                        selected_stop.service_start_time,
                        selected_stop.service_end_time,
                    )
                )

    def _build_result(
        self,
        problem: OptimizationProblem,
        solved: Any,
    ) -> OptimizationResult:
        """Проверяет найденные маршруты и собирает общие метрики проекта."""

        routes: dict[str, EngineerRoute] = {}
        assigned_ids: set[str] = set()
        unassigned_reasons: dict[str, UnassignedReason] = {}
        resource_intervals: dict[str, list[tuple[str, int, int]]] = {}

        # Timefold обычно возвращает допустимый маршрут. Повторная проверка
        # здесь нужна как защитный слой доменной модели: в результат никогда
        # не попадёт назначение, нарушающее hard constraint.
        for entity in solved.engineers:
            accepted: list[Task] = []
            for planning_task in entity.tasks:
                task = planning_task.task
                candidate = accepted + [task]
                schedule = _schedule_tasks(
                    problem, entity.engineer, entity.availability, candidate
                )
                if schedule is None or not engineer_can_execute_task(
                    problem, entity.engineer, task
                ):
                    unassigned_reasons.setdefault(
                        task.id,
                        self._reason_for_unassigned(problem, task),
                    )
                    continue
                candidate_stop = schedule[-1]
                if not _resources_are_available(
                    problem,
                    entity.engineer,
                    task,
                    candidate_stop,
                    resource_intervals,
                ):
                    unassigned_reasons.setdefault(
                        task.id,
                        UnassignedReason(
                            UnassignedReasonCode.RESOURCE_CONFLICT,
                            "Ограниченный экземпляр ресурса занят в этот интервал.",
                        ),
                    )
                    continue
                accepted.append(task)
                for resource_id in resource_ids_used_for_task(
                    problem, entity.engineer, task
                ):
                    resource_intervals.setdefault(resource_id, []).append(
                        (
                            entity.engineer.id,
                            candidate_stop.service_start_time,
                            candidate_stop.service_end_time,
                        )
                    )

            schedule = _schedule_tasks(
                problem, entity.engineer, entity.availability, accepted
            )
            assert schedule is not None
            route = _build_route(problem, entity.engineer, schedule)
            routes[entity.engineer.id] = route
            assigned_ids.update(stop.task.id for stop in schedule)

        for task in problem.tasks:
            if task.id not in assigned_ids:
                unassigned_reasons.setdefault(
                    task.id, self._reason_for_unassigned(problem, task)
                )

        unassigned_task_ids = tuple(
            task.id for task in problem.tasks if task.id in unassigned_reasons
        )
        return _build_result(
            problem,
            routes,
            unassigned_task_ids,
            unassigned_reasons,
            self.config,
        )

    @staticmethod
    def _reason_for_unassigned(
        problem: OptimizationProblem,
        task: Task,
    ) -> UnassignedReason:
        """Использует те же structured reason, что и OR-Tools."""

        if not any(engineer_can_execute_task(problem, engineer, task) for engineer in problem.engineers):
            return ORToolsOptimizer._eligibility_unassigned_reason(problem, task)
        return ORToolsOptimizer._time_unassigned_reason(problem, task)


def _schedule_tasks(
    problem: OptimizationProblem,
    engineer: Engineer,
    availability: EngineerAvailability,
    tasks: Iterable[Task],
) -> list[_ScheduledStop] | None:
    """Проверяет порядок заявок с ожиданием окна и границей смены."""

    current_time = hhmm_to_minutes(availability.available_from)
    previous_location = engineer.start_location_id
    schedule: list[_ScheduledStop] = []
    for task in tasks:
        travel_time = problem.travel_time_between(
            previous_location, task.location_id, engineer.vehicle_type
        )
        arrival_time = current_time + travel_time
        service_start = max(arrival_time, hhmm_to_minutes(task.window_start))
        service_end = service_start + task.duration_minutes
        if service_start > hhmm_to_minutes(task.window_end):
            return None
        if service_end > hhmm_to_minutes(availability.available_until):
            return None
        schedule.append(
            _ScheduledStop(
                task=task,
                arrival_time=arrival_time,
                service_start_time=service_start,
                service_end_time=service_end,
                distance_from_previous_km=problem.travel_distance_between(
                    previous_location, task.location_id, engineer.vehicle_type
                ),
            )
        )
        current_time = service_end
        previous_location = task.location_id
    return schedule


def _route_distance(problem: OptimizationProblem, engineer: Engineer, tasks: list[Task]) -> float:
    """Считает пробег маршрута без возвращения на базу."""

    schedule = _schedule_tasks(
        problem,
        engineer,
        next(item for item in problem.availabilities if item.engineer_id == engineer.id),
        tasks,
    )
    if schedule is None:
        return 0.0
    return math.fsum(stop.distance_from_previous_km for stop in schedule)


def _route_travel_time(problem: OptimizationProblem, engineer: Engineer, tasks: list[Task]) -> int:
    """Считает суммарное время движения без времени ожидания."""

    total = 0
    previous_location = engineer.start_location_id
    for task in tasks:
        total += problem.travel_time_between(
            previous_location, task.location_id, engineer.vehicle_type
        )
        previous_location = task.location_id
    return total


def _resource_conflicts_between(left: Any, right: Any) -> int:
    """Считает пересечения общих экземпляров ресурсов двух маршрутов."""

    left_schedule = left.schedule()
    right_schedule = right.schedule()
    if left_schedule is None or right_schedule is None:
        return 0
    left_by_resource: dict[str, list[tuple[int, int]]] = {}
    right_by_resource: dict[str, list[tuple[int, int]]] = {}
    for stop in left_schedule:
        for resource_id in resource_ids_used_for_task(
            left.problem, left.engineer, stop.task
        ):
            left_by_resource.setdefault(resource_id, []).append(
                (stop.service_start_time, stop.service_end_time)
            )
    for stop in right_schedule:
        for resource_id in resource_ids_used_for_task(
            right.problem, right.engineer, stop.task
        ):
            right_by_resource.setdefault(resource_id, []).append(
                (stop.service_start_time, stop.service_end_time)
            )
    conflicts = 0
    for resource_id in left_by_resource.keys() & right_by_resource.keys():
        for left_start, left_end in left_by_resource[resource_id]:
            for right_start, right_end in right_by_resource[resource_id]:
                conflicts += int(left_start < right_end and right_start < left_end)
    return conflicts


def _resources_are_available(
    problem: OptimizationProblem,
    engineer: Engineer,
    task: Task,
    stop: _ScheduledStop,
    resource_intervals: dict[str, list[tuple[str, int, int]]],
) -> bool:
    """Проверяет отсутствие пересечения экземпляров ресурсов."""

    for resource_id in resource_ids_used_for_task(problem, engineer, task):
        for _, start, end in resource_intervals.get(resource_id, []):
            if start < stop.service_end_time and stop.service_start_time < end:
                return False
    return True


def _build_route(
    problem: OptimizationProblem,
    engineer: Engineer,
    schedule: list[_ScheduledStop],
) -> EngineerRoute:
    """Преобразует внутреннее расписание в общий формат результата."""

    return EngineerRoute(
        engineer_id=engineer.id,
        stops=tuple(
            RouteStop(
                task_id=stop.task.id,
                arrival_time=minutes_to_hhmm(stop.arrival_time),
                service_start_time=minutes_to_hhmm(stop.service_start_time),
                service_end_time=minutes_to_hhmm(stop.service_end_time),
                travel_time_from_previous=problem.travel_time_between(
                    engineer.start_location_id
                    if index == 0
                    else schedule[index - 1].task.location_id,
                    stop.task.location_id,
                    engineer.vehicle_type,
                ),
                distance_from_previous_km=stop.distance_from_previous_km,
            )
            for index, stop in enumerate(schedule)
        ),
        total_travel_minutes=sum(
            problem.travel_time_between(
                engineer.start_location_id
                if index == 0
                else schedule[index - 1].task.location_id,
                stop.task.location_id,
                engineer.vehicle_type,
            )
            for index, stop in enumerate(schedule)
        ),
        total_service_minutes=sum(stop.task.duration_minutes for stop in schedule),
        total_distance_km=math.fsum(
            stop.distance_from_previous_km for stop in schedule
        ),
    )


def _build_result(
    problem: OptimizationProblem,
    routes: dict[str, EngineerRoute],
    unassigned_task_ids: tuple[str, ...],
    unassigned_reasons: dict[str, UnassignedReason],
    config: OptimizerConfig,
) -> OptimizationResult:
    """Собирает общие метрики и objective из допустимых маршрутов."""

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
    unassigned_penalty = sum(
        config.unassigned_penalty
        * (
            config.urgent_unassigned_multiplier
            if next(task for task in problem.tasks if task.id == task_id).priority.value == "URGENT"
            else config.normal_unassigned_multiplier
        )
        for task_id in unassigned_task_ids
    )
    used_engineers_penalty = used_engineers_count * config.used_engineers_penalty
    distance_penalty = int(round(total_distance * config.distance_penalty_per_km))
    travel_time_penalty = total_travel_time * config.travel_time_penalty_per_minute
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


__all__ = ["TimefoldOptimizer", "TimefoldUnavailableError"]
