"""Ручные назначения и проверка контрольного распределения.

Модуль не строит оптимальный план. Он принимает заданные человеком пары
«заявка — инженер», сохраняет порядок этих назначений и разрешает добавить
заявку только после проверки всех жёстких ограничений.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import csv
import io
import math
from pathlib import Path
from typing import Iterable, Mapping, Sequence

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
class ManualAssignment:
    """Одно ручное назначение с порядком из исходного файла."""

    task_id: str  # ID заявки из OptimizationProblem.
    engineer_id: str  # ID назначенного инженера.
    sequence: int  # Порядковый номер строки контрольного распределения.


@dataclass(frozen=True, slots=True)
class ManualAssignmentViolation:
    """Одна ошибка ручного назначения или нарушения hard constraint."""

    task_id: str  # Заявка, к которой относится нарушение.
    engineer_id: str  # Инженер из ручного назначения.
    code: str  # Машиночитаемый код причины.
    message: str  # Понятное описание для API, UI или отчёта проверки.


@dataclass(frozen=True, slots=True)
class ManualAssignmentValidation:
    """Результат проверки ручного плана без изменения самого плана."""

    violations: tuple[ManualAssignmentViolation, ...]  # Все найденные нарушения.

    @property
    def valid(self) -> bool:
        """Возвращает True, если ручной план не нарушает ограничения."""
        return not self.violations


class ManualAssignmentError(ValueError):
    """Исключение при попытке добавить недопустимое ручное назначение."""

    def __init__(self, violations: Sequence[ManualAssignmentViolation]) -> None:
        self.violations = tuple(violations)
        message = "; ".join(violation.message for violation in self.violations)
        super().__init__(message or "Ручное назначение недопустимо")


@dataclass
class ManualAssignmentPlan:
    """Изменяемый ручной план, безопасно расширяемый через ``add_task``."""

    assignments_by_engineer: dict[str, list[str]] = field(default_factory=dict)  # Заявки каждого инженера в порядке посещения.

    def validate(self, problem: OptimizationProblem) -> ManualAssignmentValidation:
        """Возвращает все нарушения текущего плана без его изменения."""
        return ManualAssignmentPlanner(self.assignments_by_engineer).validate(problem)

    def add_task(
        self,
        problem: OptimizationProblem,
        engineer_id: str,
        task_id: str,
        position: int | None = None,
    ) -> None:
        """Добавляет заявку только если новый план полностью допустим.

        Сначала строится копия текущего плана, затем проверяются навыки,
        оборудование, транспорт, окна, смены и ограниченные ресурсы. Исходный
        план изменяется только при отсутствии нарушений.
        """
        tasks_by_id = {task.id: task for task in problem.tasks}
        task = tasks_by_id.get(task_id)
        if task is None:
            raise ManualAssignmentError(
                (
                    ManualAssignmentViolation(
                        task_id,
                        engineer_id,
                        "unknown_task",
                        f"Заявка {task_id!r} отсутствует в задаче.",
                    ),
                )
            )
        if task_id not in {item.id for item in problem.planning_tasks}:
            raise ManualAssignmentError(
                (
                    ManualAssignmentViolation(
                        task_id,
                        engineer_id,
                        "inactive_task",
                        f"Заявка {task_id} уже завершена или отменена и не может "
                        "быть добавлена в новый маршрут.",
                    ),
                )
            )
        candidate = {
            current_engineer_id: list(task_ids)
            for current_engineer_id, task_ids in self.assignments_by_engineer.items()
        }
        task_ids = candidate.setdefault(engineer_id, [])
        if position is None:
            task_ids.append(task_id)
        else:
            task_ids.insert(position, task_id)
        validation = ManualAssignmentPlanner(candidate).validate(problem)
        if not validation.valid:
            raise ManualAssignmentError(validation.violations)
        self.assignments_by_engineer = candidate


@dataclass(frozen=True, slots=True)
class ControlDataset:
    """Контрольные назначения из CSV и результат сверки с JSON."""

    assignments: tuple[ManualAssignment, ...]  # Назначения в порядке строк CSV.
    status_by_task: Mapping[str, TaskStatus]  # Статус каждой строки CSV.
    consistency_errors: tuple[str, ...]  # Противоречия между CSV и JsonScenario.

    @property
    def consistent(self) -> bool:
        """Возвращает True, если CSV и JSON согласованы."""
        return not self.consistency_errors

    def plan(
        self,
        tasks: Mapping[str, Task] | None = None,
    ) -> ManualAssignmentPlan:
        """Преобразует строки CSV в ручной план.

        Без ``tasks`` сохраняется порядок строк CSV. Если передана карта
        заявок, назначения внутри каждого экипажа сортируются по началу окна,
        а исходный номер строки используется для стабильного порядка заявок
        с одинаковым окном. В CSV есть исполнитель, но нет порядка визитов,
        поэтому такой режим нужен для честной проверки выполнимого расписания.
        """
        assignments_by_engineer: dict[str, list[str]] = {}
        assignments = self.assignments
        if tasks is not None:
            assignments_by_engineer = {}
            for assignment in assignments:
                assignments_by_engineer.setdefault(assignment.engineer_id, []).append(
                    assignment.task_id
                )
            for engineer_id, task_ids in assignments_by_engineer.items():
                assignments_by_engineer[engineer_id] = sorted(
                    task_ids,
                    key=lambda task_id: (
                        hhmm_to_minutes(tasks[task_id].window_start),
                        next(
                            item.sequence
                            for item in assignments
                            if item.task_id == task_id
                            and item.engineer_id == engineer_id
                        ),
                    ),
                )
            return ManualAssignmentPlan(assignments_by_engineer)
        for assignment in assignments:
            assignments_by_engineer.setdefault(assignment.engineer_id, []).append(
                assignment.task_id
            )
        return ManualAssignmentPlan(assignments_by_engineer)


class ManualAssignmentPlanner(RouteOptimizer):
    """Строит результат для заранее заданных ручных назначений."""

    def __init__(
        self,
        assignments_by_engineer: Mapping[str, Sequence[str]],
        config: OptimizerConfig | None = None,
    ) -> None:
        """Создаёт planner, сохраняя порядок заявок каждой группы."""
        self.assignments_by_engineer = {
            engineer_id: tuple(task_ids)
            for engineer_id, task_ids in assignments_by_engineer.items()
        }
        self.config = config or OptimizerConfig()

    def validate(self, problem: OptimizationProblem) -> ManualAssignmentValidation:
        """Проверяет ручные назначения без запуска OR-Tools и без мутаций."""
        engineers_by_id = {engineer.id: engineer for engineer in problem.engineers}
        tasks_by_id = {task.id: task for task in problem.tasks}
        planning_task_ids = {task.id for task in problem.planning_tasks}
        availability_by_engineer = {
            availability.engineer_id: availability
            for availability in problem.availabilities
        }
        violations: list[ManualAssignmentViolation] = []
        assigned_task_ids: set[str] = set()
        resource_intervals: dict[str, list[tuple[str, int, int]]] = {}

        for engineer_id, task_ids in self.assignments_by_engineer.items():
            engineer = engineers_by_id.get(engineer_id)
            if engineer is None:
                for task_id in task_ids:
                    violations.append(
                        ManualAssignmentViolation(
                            task_id,
                            engineer_id,
                            "unknown_engineer",
                            f"Инженер {engineer_id!r} отсутствует в задаче.",
                        )
                    )
                continue
            availability = availability_by_engineer[engineer_id]
            current_time = hhmm_to_minutes(availability.available_from)
            previous_location = engineer.start_location_id
            for task_id in task_ids:
                task = tasks_by_id.get(task_id)
                if task is None:
                    violations.append(
                        ManualAssignmentViolation(
                            task_id,
                            engineer_id,
                            "unknown_task",
                            f"Заявка {task_id!r} отсутствует в задаче.",
                        )
                    )
                    continue
                # Статусная политика едина для всех planner'ов: выполненные и
                # отменённые заявки известны системе, но не входят в новый
                # маршрут. Поэтому строка контрольного плана не считается ни
                # назначением, ни ошибкой hard constraints.
                if task_id not in planning_task_ids:
                    continue
                if task_id in assigned_task_ids:
                    violations.append(
                        ManualAssignmentViolation(
                            task_id,
                            engineer_id,
                            "duplicate_task",
                            f"Заявка {task_id} назначена более одного раза.",
                        )
                    )
                assigned_task_ids.add(task_id)

                violation = self._compatibility_violation(problem, engineer, task)
                if violation is not None:
                    violations.append(
                        ManualAssignmentViolation(
                            task.id,
                            engineer_id,
                            violation.code.value,
                            violation.message,
                        )
                    )
                    continue

                travel_time = problem.travel_time_between(
                    previous_location,
                    task.location_id,
                    engineer.vehicle_type,
                )
                arrival_time = current_time + travel_time
                service_start = max(arrival_time, hhmm_to_minutes(task.window_start))
                service_end = service_start + task.duration_minutes
                if service_start > hhmm_to_minutes(task.window_end):
                    violations.append(
                        ManualAssignmentViolation(
                            task.id,
                            engineer_id,
                            UnassignedReasonCode.IMPOSSIBLE_TIME_WINDOW.value,
                            f"Заявка {task.id} не начинается в окне "
                            f"{task.window_start}–{task.window_end}.",
                        )
                    )
                if service_end > hhmm_to_minutes(availability.available_until):
                    violations.append(
                        ManualAssignmentViolation(
                            task.id,
                            engineer_id,
                            UnassignedReasonCode.OUTSIDE_WORKING_HOURS.value,
                            f"Заявка {task.id} заканчивается после смены "
                            f"инженера {availability.available_until}.",
                        )
                    )
                if service_start <= hhmm_to_minutes(task.window_end) and service_end <= hhmm_to_minutes(availability.available_until):
                    for resource_id in resource_ids_used_for_task(problem, engineer, task):
                        for other_engineer_id, other_start, other_end in resource_intervals.get(resource_id, ()):
                            if service_start < other_end and other_start < service_end:
                                violations.append(
                                    ManualAssignmentViolation(
                                        task.id,
                                        engineer_id,
                                        UnassignedReasonCode.RESOURCE_CONFLICT.value,
                                        f"Ресурс {resource_id} уже занят в это время.",
                                    )
                                )
                        resource_intervals.setdefault(resource_id, []).append(
                            (engineer_id, service_start, service_end)
                        )
                current_time = service_end
                previous_location = task.location_id

        return ManualAssignmentValidation(tuple(violations))

    def optimize(self, problem: OptimizationProblem) -> OptimizationResult:
        """Строит контрольный результат или отклоняет нарушающий план."""
        validation = self.validate(problem)
        if not validation.valid:
            raise ManualAssignmentError(validation.violations)

        tasks_by_id = {task.id: task for task in problem.tasks}
        planning_task_ids = {task.id for task in problem.planning_tasks}
        availability_by_engineer = {
            availability.engineer_id: availability
            for availability in problem.availabilities
        }
        routes: dict[str, EngineerRoute] = {}
        assigned_task_ids: set[str] = set()
        for engineer in problem.engineers:
            route_tasks = [
                tasks_by_id[task_id]
                for task_id in self.assignments_by_engineer.get(engineer.id, ())
                if task_id in planning_task_ids
            ]
            routes[engineer.id] = self._build_route(
                engineer,
                availability_by_engineer[engineer.id],
                route_tasks,
                problem,
            )
            assigned_task_ids.update(task.id for task in route_tasks)

        unassigned_task_ids = tuple(
            task.id
            for task in problem.planning_tasks
            if task.id not in assigned_task_ids
        )
        unassigned_reasons = {
            task_id: UnassignedReason(
                UnassignedReasonCode.OUTSIDE_WORKING_HOURS,
                "Заявка отсутствует в ручном распределении.",
            )
            for task_id in unassigned_task_ids
        }
        total_distance = math.fsum(
            route.total_distance_km for route in routes.values()
        )
        total_travel_time = sum(
            route.total_travel_minutes for route in routes.values()
        )
        used_engineers_count = sum(bool(route.stops) for route in routes.values())
        distance_by_engineer = {
            engineer_id: route.total_distance_km
            for engineer_id, route in routes.items()
        }
        travel_time_by_engineer = {
            engineer_id: route.total_travel_minutes
            for engineer_id, route in routes.items()
        }
        unassigned_penalty = sum(
            self.config.unassigned_penalty
            * self._priority_multiplier(tasks_by_id[task_id])
            for task_id in unassigned_task_ids
        )
        used_engineers_penalty = used_engineers_count * self.config.used_engineers_penalty
        distance_penalty = int(round(total_distance * self.config.distance_penalty_per_km))
        travel_time_penalty = total_travel_time * self.config.travel_time_penalty_per_minute
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

    @staticmethod
    def _compatibility_violation(
        problem: OptimizationProblem,
        engineer: Engineer,
        task: Task,
    ) -> UnassignedReason | None:
        """Возвращает первую нарушенную совместимость инженера и заявки."""
        if not task.required_skills.issubset(engineer.qualifications):
            return UnassignedReason(
                UnassignedReasonCode.MISSING_QUALIFICATION,
                "У инженера нет требуемой квалификации.",
            )
        if not engineer_has_required_equipment(problem, engineer, task):
            return UnassignedReason(
                UnassignedReasonCode.MISSING_EQUIPMENT,
                "У инженера нет требуемого оборудования.",
            )
        if not engineer_can_execute_task(problem, engineer, task):
            return UnassignedReason(
                UnassignedReasonCode.MISSING_VEHICLE_TYPE,
                "Тип транспорта инженера не соответствует заявке.",
            )
        return None

    def _build_route(
        self,
        engineer: Engineer,
        availability: EngineerAvailability,
        tasks: Sequence[Task],
        problem: OptimizationProblem,
    ) -> EngineerRoute:
        """Преобразует утверждённый порядок заявок в доменный маршрут."""
        current_time = hhmm_to_minutes(availability.available_from)
        previous_location = engineer.start_location_id
        stops: list[RouteStop] = []
        total_travel = 0
        total_distance = 0.0
        total_service = 0
        for task in tasks:
            travel_time = problem.travel_time_between(
                previous_location,
                task.location_id,
                engineer.vehicle_type,
            )
            arrival_time = current_time + travel_time
            service_start = max(arrival_time, hhmm_to_minutes(task.window_start))
            service_end = service_start + task.duration_minutes
            distance = problem.travel_distance_between(
                previous_location,
                task.location_id,
                engineer.vehicle_type,
            )
            stops.append(
                RouteStop(
                    task_id=task.id,
                    arrival_time=minutes_to_hhmm(arrival_time),
                    service_start_time=minutes_to_hhmm(service_start),
                    service_end_time=minutes_to_hhmm(service_end),
                    travel_time_from_previous=travel_time,
                    distance_from_previous_km=distance,
                )
            )
            current_time = service_end
            previous_location = task.location_id
            total_travel += travel_time
            total_distance += distance
            total_service += task.duration_minutes
        return EngineerRoute(
            engineer_id=engineer.id,
            stops=tuple(stops),
            total_travel_minutes=total_travel,
            total_service_minutes=total_service,
            total_distance_km=total_distance,
        )

    def _priority_multiplier(self, task: Task) -> int:
        """Возвращает коэффициент штрафа за неназначение из конфигурации."""
        return (
            self.config.urgent_unassigned_multiplier
            if task.priority.value == "URGENT"
            else self.config.normal_unassigned_multiplier
        )


_CSV_STATUS = {
    "не отправлена": TaskStatus.NOT_SENT,
    "отправлена": TaskStatus.ASSIGNED,
    "назначена": TaskStatus.ASSIGNED,
    "в пути": TaskStatus.EN_ROUTE,
    "в работе": TaskStatus.IN_PROGRESS,
    "выполнена": TaskStatus.COMPLETED,
    "отменена": TaskStatus.CANCELLED,
    "просрочена": TaskStatus.OVERDUE,
}


def load_control_dataset(path: str | Path, scenario) -> ControlDataset:
    """Загружает CSV контрольного распределения и сверяет его с JSON.

    Импорт не зашит под один dataset: номер заявки из CSV сопоставляется с
    последней частью ``Task.id``. Поэтому тот же код можно применять к двум
    следующим файлам после передачи нового пути и нового ``JsonScenario``.
    """
    tasks_by_suffix = {
        task.id.rsplit("J", 1)[-1]: task for task in scenario.tasks
    }
    tasks_by_control_id = {
        control_id: next(task for task in scenario.tasks if task.id == task_id)
        for task_id, control_id in scenario.control_request_id_by_task.items()
    }
    engineers_by_name = {engineer.name: engineer for engineer in scenario.engineers}
    reference_by_task = scenario.reference_engineer_by_task
    status_by_task: dict[str, TaskStatus] = {}
    assignments: list[ManualAssignment] = []
    errors: list[str] = []
    seen_task_ids: set[str] = set()

    raw_csv = Path(path).read_bytes()
    decoded_csv: str | None = None
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            decoded_csv = raw_csv.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded_csv is None:
        raise ValueError(f"Не удалось прочитать контрольный CSV {path}")
    reader = csv.DictReader(io.StringIO(decoded_csv), delimiter=";")
    required_columns = {"Заявка", "Начало", "Окончание", "Бригада", "Статус BK"}
    missing_columns = required_columns - set(reader.fieldnames or ())
    if missing_columns:
        raise ValueError(f"В контрольном CSV отсутствуют колонки: {sorted(missing_columns)}")
    for row_number, row in enumerate(reader, start=2):
        suffix = (row.get("Заявка") or "").strip()
        task = tasks_by_suffix.get(suffix) or tasks_by_control_id.get(suffix)
        if task is None:
            errors.append(f"Строка {row_number}: заявка {suffix!r} отсутствует в JSON.")
            continue
        task_id = task.id
        seen_task_ids.add(task_id)
        engineer_name = (row.get("Бригада") or "").strip()
        engineer = engineers_by_name.get(engineer_name)
        if engineer is None:
            errors.append(f"Строка {row_number}: инженер {engineer_name!r} отсутствует в JSON.")
            continue
        raw_status = (row.get("Статус BK") or "").strip().lower()
        status = _CSV_STATUS.get(raw_status)
        if status is None:
            errors.append(f"Строка {row_number}: неизвестный статус {raw_status!r}.")
        else:
            status_by_task[task_id] = status
            if status != scenario.reference_status_by_task.get(task_id):
                errors.append(
                    f"Строка {row_number}: статус заявки {task_id} не совпадает с JSON."
                )
        csv_window = (
            (row.get("Начало") or "").strip().split()[-1],
            (row.get("Окончание") or "").strip().split()[-1],
        )
        if csv_window != (task.window_start, task.window_end):
            errors.append(
                f"Строка {row_number}: окно заявки {task_id} не совпадает с JSON."
            )
        if engineer_name != reference_by_task.get(task_id):
            errors.append(
                f"Строка {row_number}: исполнитель заявки {task_id} не совпадает с JSON."
            )
        assignments.append(
            ManualAssignment(task_id, engineer.id, row_number)
        )

    missing_tasks = set(tasks_by_suffix.values()) - {
        task for task in scenario.tasks if task.id in seen_task_ids
    }
    if missing_tasks:
        errors.append(
            "В CSV отсутствуют заявки из JSON: "
            + ", ".join(sorted(task.id for task in missing_tasks))
        )
    if len(assignments) != len(seen_task_ids):
        errors.append("В CSV есть повторяющиеся заявки или строки без сопоставленного ID.")
    return ControlDataset(tuple(assignments), status_by_task, tuple(errors))
