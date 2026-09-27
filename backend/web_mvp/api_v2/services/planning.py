"""Сервисный слой web MVP между REST API и Optimization Engine."""

from __future__ import annotations

import json
import os
from uuid import uuid4
from dataclasses import replace
from pathlib import Path
from typing import Any

from backend.optimization import (
    CoordinateRoutingProvider,
    EngineerOperationalState,
    EngineerRoute,
    JsonScenario,
    OptimizationProblem,
    OptimizationResult,
    OptimizerConfig,
    GreedyBaselineOptimizer,
    ORToolsOptimizer,
    OSRMRoutingProvider,
    create_osrm_provider_from_environment,
    ExplanationEngine,
    RoutingProvider,
    Priority,
    Skill,
    Task,
    TaskStatus,
    VehicleType,
    WORK_NORMS,
    WorkType,
    load_json_scenario,
    load_json_scenario_data,
)
from backend.optimization.scripts.generate_dataset_json import NominatimGeocoder
from backend.optimization.constraints import engineer_has_required_equipment
from backend.optimization.manual_planner import (
    ManualAssignmentPlanner,
    load_control_dataset_from_scenario,
)
from backend.web_mvp.api_v2.serializers.optimization import OptimizationResultSerializer, DatasetSerializer


PROJECT_ROOT = Path(__file__).resolve().parents[4]
OFFICIAL_DATASET_PATH = PROJECT_ROOT / "Югоцентр.json"
OFFICIAL_DATASET_PATHS = tuple(
    PROJECT_ROOT / filename
    for filename in ("Восток.json", "Юго-восток.json", "Югоцентр.json")
)


class PlanningService:
    """Хранит выбранный dataset и вызывает независимое математическое ядро.

    Состояние хранится в памяти, потому что MVP рассчитан на одного локального
    пользователя. Позже этот класс можно заменить репозиторием без изменений
    в Optimization Engine.
    """

    def __init__(self) -> None:
        """Создаёт сервис без загруженного пользовательского сценария."""
        self._scenario: JsonScenario | None = None
        self._source_name: str | None = None
        self.routing_provider: RoutingProvider | None = None
        self._routing_provider_requires_rebuild = False
        self.use_osrm = True
        self._problem: OptimizationProblem | None = None
        self._result: OptimizationResult | None = None
        self._preserve_assigned_tasks = False
        self._ignore_task_statuses = False
        self._consider_equipment = False
        self._manual_status_update = False
        self._unavailable_engineer_ids: set[str] = set()
        self._geocoder: NominatimGeocoder | None = None
        self._manual_reassignment_proposals: dict[str, dict[str, Any]] = {}
        # После условных 14:00 новые обычные заявки разрешено распределять
        # только между инженерами, которые уже находились на линии.
        self._late_day_manual_task_ids: set[str] = set()
        self._late_day_active_engineer_ids: set[str] = set()

    def reset(self) -> None:
        """Очищает dataset; используется тестами и локальной перезагрузкой."""
        self._scenario = None
        self._source_name = None
        self.routing_provider = None
        self._routing_provider_requires_rebuild = False
        self._problem = None
        self._result = None
        self._preserve_assigned_tasks = False
        self._ignore_task_statuses = False
        self._consider_equipment = False
        self._unavailable_engineer_ids = set()
        self._manual_reassignment_proposals.clear()
        self._late_day_manual_task_ids.clear()
        self._late_day_active_engineer_ids.clear()

    def load_official_dataset(self) -> JsonScenario:
        """Загружает официальный демонстрационный JSON из корня проекта."""
        scenario = load_json_scenario(OFFICIAL_DATASET_PATH)
        self._scenario = scenario
        self._source_name = OFFICIAL_DATASET_PATH.name
        self._problem = None
        self._result = None
        self._preserve_assigned_tasks = False
        self._ignore_task_statuses = False
        self._unavailable_engineer_ids = set()
        self._manual_reassignment_proposals.clear()
        self._late_day_manual_task_ids.clear()
        self._late_day_active_engineer_ids.clear()
        # У нового dataset другой набор координат, поэтому старый provider и
        # его кэш ответов больше нельзя использовать.
        self.routing_provider = None
        self._routing_provider_requires_rebuild = False
        self._unavailable_engineer_ids = set()
        return scenario

    def load_uploaded_dataset(self, content: bytes, filename: str) -> JsonScenario:
        """Разбирает загруженный JSON и делает его текущим dataset."""
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Файл должен содержать корректный JSON в UTF-8") from exc
        scenario = load_json_scenario_data(payload)
        self._scenario = scenario
        self._source_name = filename
        self._problem = None
        self._result = None
        self._preserve_assigned_tasks = False
        self.routing_provider = None
        self._routing_provider_requires_rebuild = False
        self._manual_reassignment_proposals.clear()
        self._late_day_manual_task_ids.clear()
        self._late_day_active_engineer_ids.clear()
        return scenario

    def current_dataset(self) -> JsonScenario:
        """Возвращает текущий dataset, по умолчанию официальный."""
        if self._scenario is None:
            return self.load_official_dataset()
        return self._scenario

    def apply_reference_distribution(
        self,
        scenario: JsonScenario,
        source_name: str,
    ) -> tuple[JsonScenario, OptimizationResult]:
        """Полностью заменяет рабочее состояние контрольным планом из JSON."""
        self.reset()
        self._scenario = scenario
        self._source_name = source_name
        self._ignore_task_statuses = False
        self._preserve_assigned_tasks = False
        problem = self._build_problem(scenario)
        control = load_control_dataset_from_scenario(scenario)
        if not control.consistent:
            raise ValueError("; ".join(control.consistency_errors))
        planner = ManualAssignmentPlanner(
            control.plan(
                {task.id: task for task in problem.tasks},
                sort_by_window=False,
            ).assignments_by_engineer
        )
        validation = planner.validate(problem)
        if not validation.valid:
            raise ValueError(
                "; ".join(violation.message for violation in validation.violations)
            )
        self._problem = problem
        self._result = planner.optimize(problem)
        return scenario, self._result

    def optimize_current(
        self,
        preserve_assigned_tasks: bool = False,
        ignore_task_statuses: bool = False,
        solver: str = "ortools",
        planning_time: str | None = None,
        operational_states: tuple[EngineerOperationalState, ...] = (),
        initial_routes_by_engineer: dict[str, tuple[str, ...]] | None = None,
        reference_routes_by_engineer: dict[str, tuple[str, ...]] | None = None,
        consider_equipment: bool = False,
    ) -> tuple[JsonScenario, OptimizationResult]:
        """Строит задачу и запускает выбранный solver для текущего dataset.

        ``baseline`` используется интерфейсом как простой первый расчёт. Он
        получает ту же OptimizationProblem и возвращает тот же формат ответа,
        что и OR-Tools, но не выполняет глобальный поиск.
        """
        if solver not in {"ortools", "baseline"}:
            raise ValueError("solver должен быть 'ortools' или 'baseline'.")
        scenario = self.current_dataset()
        current_routes: dict[str, tuple[str, ...]] | None = None
        if not ignore_task_statuses and self._result is not None:
            plannable_task_ids = {
                task.id
                for task in scenario.tasks
                if task.status not in {TaskStatus.CANCELLED, TaskStatus.COMPLETED}
            }
            current_routes = {
                engineer_id: tuple(
                    stop.task_id
                    for stop in route.stops
                    if stop.task_id in plannable_task_ids
                )
                for engineer_id, route in self._result.routes.items()
            }
            if initial_routes_by_engineer is None:
                initial_routes_by_engineer = current_routes
            if reference_routes_by_engineer is None:
                reference_routes_by_engineer = current_routes
        if not ignore_task_statuses and not planning_time:
            # Контрольный снимок относится к минимальному моменту, когда все
            # уже выполняемые заявки могли начаться в своих окнах. Для этого
            # достаточно взять самое позднее начало окна среди IN_PROGRESS.
            active_window_starts = [
                task.window_start
                for task in scenario.tasks
                if task.status == TaskStatus.IN_PROGRESS
            ]
            planning_time = max(active_window_starts, default=None)
        self._preserve_assigned_tasks = preserve_assigned_tasks
        self._ignore_task_statuses = ignore_task_statuses
        self._consider_equipment = consider_equipment
        states = self._complete_operational_states(
            scenario, planning_time, operational_states
        )
        problem = self._build_problem(
            scenario,
            planning_time=planning_time,
            operational_states=states,
        )
        if solver == "baseline" and current_routes:
            # Baseline проходит заявки в порядке входных данных. Сначала
            # ставим уже рассчитанные маршруты в их фактическом порядке, а
            # затем новые неназначенные заявки. Так жадный алгоритм только
            # дополняет план и не переставляет прежние остановки.
            task_by_id = {task.id: task for task in problem.tasks}
            ordered_ids = [
                task_id
                for engineer in problem.engineers
                for task_id in current_routes.get(engineer.id, ())
                if task_id in task_by_id
            ]
            existing_ids = set(ordered_ids)
            ordered_ids.extend(
                task.id for task in problem.tasks if task.id not in existing_ids
            )
            problem = replace(
                problem,
                tasks=tuple(task_by_id[task_id] for task_id in ordered_ids),
            )
        config = OptimizerConfig(time_limit_minutes=1)
        if solver == "baseline":
            result = GreedyBaselineOptimizer(config).optimize(problem)
        else:
            # Для интерактивного MVP оставляем короткий лимит поиска. Он
            # является параметром OR-Tools, а не ограничением корректности
            # hard constraints.
            result = ORToolsOptimizer(config).optimize(
                problem,
                initial_routes_by_engineer=initial_routes_by_engineer,
                reference_routes_by_engineer=reference_routes_by_engineer,
            )
        self._validate_late_day_engineer_activation(scenario, result)
        self._problem = problem
        self._result = result
        self._manual_reassignment_proposals.clear()
        return scenario, result

    def _project_result_to_scenario(self) -> None:
        """Переносит фактические назначения из результата в текущий dataset.

        JSON содержит контрольные статусы, но после расчёта источником
        оперативного состояния становится построенный маршрут. Проекция
        нужна для сохранения этого состояния в БД: последующее перепланирование
        должно продолжаться от текущего плана, а не от reference-данных.
        """
        if self._scenario is None or self._result is None:
            return

        engineer_by_task = {
            stop.task_id: engineer_id
            for engineer_id, route in self._result.routes.items()
            for stop in route.stops
        }
        tasks = []
        for task in self._scenario.tasks:
            engineer_id = engineer_by_task.get(task.id)
            if engineer_id is not None:
                # В полном утреннем расчёте reference_status игнорируется:
                # даже заявка, которая была «В работе» в контрольном CSV,
                # становится обычной ASSIGNED-заявкой нового плана. Иначе
                # несколько исторических заявок могли оказаться «В работе»
                # одновременно у одного инженера при следующем запросе.
                status = TaskStatus.ASSIGNED
                if not self._ignore_task_statuses and task.status in {
                    TaskStatus.EN_ROUTE,
                    TaskStatus.IN_PROGRESS,
                    TaskStatus.COMPLETED,
                    TaskStatus.CANCELLED,
                    TaskStatus.OVERDUE,
                }:
                    status = task.status
                tasks.append(
                    replace(
                        task,
                        status=status,
                        current_engineer_id=engineer_id,
                    )
                )
            elif task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
                tasks.append(replace(task, current_engineer_id=None))
            else:
                tasks.append(
                    replace(
                        task,
                        status=TaskStatus.NOT_SENT,
                        current_engineer_id=None,
                    )
                )
        self._scenario = replace(self._scenario, tasks=tuple(tasks))

    def update_task_status(
        self, task_id: str, status: TaskStatus
    ) -> JsonScenario:
        """Меняет статус заявки в текущем плане без запуска solver.

        Для заявки, которая уже назначена маршруту или имеет текущего
        исполнителя, разрешены рабочие и закрывающие статусы. У заявки без
        исполнителя единственное допустимое ручное действие — отмена.
        Такой метод намеренно не перестраивает маршрут: диспетчер фиксирует
        факт, а отдельное действие перепланирования запускается явно.
        """
        if self._scenario is None:
            raise ValueError("Сначала загрузите dataset")
        if not isinstance(status, TaskStatus):
            status = TaskStatus(status)

        route_task_ids = {
            stop.task_id
            for route in (self._result.routes.values() if self._result else ())
            for stop in route.stops
        }
        tasks = list(self._scenario.tasks)
        for index, task in enumerate(tasks):
            if task.id != task_id:
                continue
            # В официальном JSON current_engineer_id может содержать
            # исполнителя из контрольного распределения при статусе NOT_SENT.
            # Такой исторический reference не считается текущим назначением.
            assigned = task.id in route_task_ids or (
                self._result is not None
                and task.current_engineer_id is not None
                and task.status
                in {
                    TaskStatus.ASSIGNED,
                    TaskStatus.EN_ROUTE,
                    TaskStatus.IN_PROGRESS,
                    TaskStatus.OVERDUE,
                    TaskStatus.COMPLETED,
                    TaskStatus.CANCELLED,
                }
            )
            allowed_statuses = (
                {
                    TaskStatus.ASSIGNED,
                    TaskStatus.EN_ROUTE,
                    TaskStatus.IN_PROGRESS,
                    TaskStatus.OVERDUE,
                    TaskStatus.COMPLETED,
                    TaskStatus.CANCELLED,
                }
                if assigned
                else {TaskStatus.CANCELLED}
            )
            if status not in allowed_statuses:
                raise ValueError(
                    (
                        f"Для назначенной заявки {task_id} допустимы статусы: "
                        "ASSIGNED, EN_ROUTE, IN_PROGRESS, OVERDUE, COMPLETED, CANCELLED."
                    )
                    if assigned
                    else f"Неназначенную заявку {task_id} можно только отменить."
                )
            current_engineer_id = task.current_engineer_id if assigned else None
            if current_engineer_id is None and self._result is not None:
                current_engineer_id = next(
                    (
                        engineer_id
                        for engineer_id, route in self._result.routes.items()
                        if any(stop.task_id == task_id for stop in route.stops)
                    ),
                    None,
                )
            tasks[index] = replace(
                task,
                status=status,
                current_engineer_id=current_engineer_id,
            )
            self._scenario = replace(self._scenario, tasks=tuple(tasks))
            # Следующее сохранение должно считать новый operational status
            # источником истины, а не контрольным JSON.
            self._ignore_task_statuses = False
            self._manual_status_update = True
            if self._problem is not None:
                self._problem = replace(self._problem, tasks=tuple(tasks))
            return self._scenario
        raise ValueError(f"Заявка {task_id!r} не найдена")

    def _filter_result_tasks(self, keep_task_ids: set[str]) -> OptimizationResult:
        """Удаляет из сохранённого результата заявки вне текущего плана."""
        assert self._result is not None
        assert self._problem is not None
        tasks_by_id = {task.id: task for task in self._scenario.tasks}
        engineers_by_id = {engineer.id: engineer for engineer in self._problem.engineers}
        routes: dict[str, EngineerRoute] = {}
        for engineer_id, route in self._result.routes.items():
            engineer = engineers_by_id[engineer_id]
            stops = tuple(
                stop for stop in route.stops if stop.task_id in keep_task_ids
            )
            distance_by_stop: list[float] = []
            travel_by_stop: list[int] = []
            previous_location = self._problem.route_start_location(engineer)
            for stop in stops:
                task = tasks_by_id[stop.task_id]
                distance_by_stop.append(
                    self._problem.travel_distance_between(
                        previous_location,
                        task.location_id,
                        engineer.vehicle_type,
                    )
                )
                travel_by_stop.append(
                    self._problem.travel_time_between(
                        previous_location,
                        task.location_id,
                        engineer.vehicle_type,
                    )
                )
                previous_location = task.location_id
            routes[engineer_id] = replace(
                route,
                stops=stops,
                total_travel_minutes=sum(travel_by_stop),
                total_service_minutes=sum(
                    tasks_by_id[stop.task_id].duration_minutes for stop in stops
                ),
                total_distance_km=sum(distance_by_stop),
            )

        distance_by_engineer = {
            engineer_id: route.total_distance_km
            for engineer_id, route in routes.items()
        }
        travel_time_by_engineer = {
            engineer_id: route.total_travel_minutes
            for engineer_id, route in routes.items()
        }
        total_distance = sum(distance_by_engineer.values())
        total_travel_time = sum(travel_time_by_engineer.values())
        used_engineers_count = sum(bool(route.stops) for route in routes.values())
        config = OptimizerConfig(time_limit_minutes=1)
        unassigned_penalty = sum(
            config.unassigned_penalty * config.unassigned_multiplier(tasks_by_id[task_id])
            for task_id in self._result.unassigned_task_ids
            if task_id in tasks_by_id
        )
        used_engineers_penalty = used_engineers_count * config.used_engineers_penalty
        distance_penalty = round(total_distance * config.distance_penalty_per_km)
        travel_time_penalty = total_travel_time * config.travel_time_penalty_per_minute
        return replace(
            self._result,
            routes=routes,
            distance_by_engineer=distance_by_engineer,
            total_distance=total_distance,
            travel_time_by_engineer=travel_time_by_engineer,
            total_travel_time=total_travel_time,
            used_engineers_count=used_engineers_count,
            assigned_task_count=sum(len(route.stops) for route in routes.values()),
            unassigned_penalty=unassigned_penalty,
            used_engineers_penalty=used_engineers_penalty,
            distance_penalty=distance_penalty,
            travel_time_penalty=travel_time_penalty,
            total_service_minutes=sum(
                route.total_service_minutes for route in routes.values()
            ),
            total_objective=(
                unassigned_penalty
                + used_engineers_penalty
                + distance_penalty
                + travel_time_penalty
                + self._result.plan_disruption_penalty
            ),
        )

    def preview_manual_reassignment(
        self,
        task_id: str,
        engineer_id: str,
    ) -> dict[str, Any]:
        """Проверяет перенос заявки и рассчитывает метрики без изменения плана."""
        if self._problem is None or self._result is None:
            raise ValueError("Сначала запустите оптимизацию")

        task = next((item for item in self._problem.tasks if item.id == task_id), None)
        engineer = next(
            (item for item in self._problem.engineers if item.id == engineer_id), None
        )
        if task is None:
            raise ValueError(f"Заявка {task_id!r} не найдена")
        if engineer is None:
            raise ValueError(f"Инженер {engineer_id!r} не найден")

        current_engineer_id = next(
            (
                route_engineer_id
                for route_engineer_id, route in self._result.routes.items()
                if any(stop.task_id == task_id for stop in route.stops)
            ),
            None,
        )
        if current_engineer_id == engineer_id:
            return self._infeasible_reassignment(
                "ALREADY_ASSIGNED",
                f"Заявка {task_id} уже назначена инженеру {engineer.name}.",
            )
        if (
            not self._ignore_task_statuses
            and task.status in {TaskStatus.CANCELLED, TaskStatus.COMPLETED}
        ):
            return self._infeasible_reassignment(
                "TASK_CLOSED",
                f"Заявка {task_id} закрыта со статусом «{task.status.value}» и не перепланируется.",
            )
        if (
            not self._ignore_task_statuses
            and task.status in {TaskStatus.EN_ROUTE, TaskStatus.IN_PROGRESS}
        ):
            return self._infeasible_reassignment(
                "ASSIGNMENT_LOCKED",
                f"Заявка {task_id} уже начата: её исполнитель зафиксирован.",
            )
        if engineer.id in self._problem.unavailable_engineer_ids:
            return self._infeasible_reassignment(
                "ENGINEER_UNAVAILABLE",
                f"Инженер {engineer.name} недоступен в рассматриваемый период.",
            )
        if not task.required_skills.issubset(engineer.qualifications):
            required = ", ".join(sorted(skill.value for skill in task.required_skills))
            return self._infeasible_reassignment(
                "MISSING_SKILL",
                f"У инженера {engineer.name} нет требуемой квалификации: {required}.",
            )
        if not engineer_has_required_equipment(self._problem, engineer, task):
            missing = ", ".join(sorted(task.required_equipment - engineer.available_equipment))
            available_routers = self._problem.available_router_count_for_planning(
                engineer
            )
            if task.required_router_count > available_routers:
                return self._infeasible_reassignment(
                    "MISSING_EQUIPMENT",
                    f"Для заявки требуется {task.required_router_count} роутеров, "
                    f"у инженера {engineer.name} доступно {available_routers}.",
                )
            return self._infeasible_reassignment(
                "MISSING_EQUIPMENT",
                f"У инженера {engineer.name} нет обязательного оборудования: {missing}.",
            )
        if (
            task.required_vehicle_type is not None
            and task.required_vehicle_type != engineer.vehicle_type
        ):
            return self._infeasible_reassignment(
                "VEHICLE_MISMATCH",
                f"Для заявки нужен транспорт {task.required_vehicle_type.value}, "
                f"у инженера {engineer.name} — {engineer.vehicle_type.value}.",
            )

        current_routes = {
            route_engineer_id: tuple(stop.task_id for stop in route.stops)
            for route_engineer_id, route in self._result.routes.items()
        }
        try:
            candidate_result = ORToolsOptimizer(
                OptimizerConfig(time_limit_minutes=1)
            ).optimize(
                self._problem,
                forced_task_engineer_by_id={task_id: engineer_id},
                initial_routes_by_engineer=current_routes,
                reference_routes_by_engineer=current_routes,
                time_limit_seconds=5,
            )
        except ValueError:
            return self._infeasible_reassignment(
                "SCHEDULE_INFEASIBLE",
                "Переназначение нарушает временное окно заявки, рабочую смену "
                "или расписание других заявок инженера.",
            )

        target_route = candidate_result.routes[engineer_id]
        if not any(stop.task_id == task_id for stop in target_route.stops):
            return self._infeasible_reassignment(
                "SCHEDULE_INFEASIBLE",
                "OR-Tools не нашёл допустимый маршрут с выбранным исполнителем.",
            )

        proposal_id = uuid4().hex
        before = self._main_metrics(self._result)
        after = self._main_metrics(candidate_result)
        old_engineer = next(
            (item for item in self._problem.engineers if item.id == current_engineer_id),
            None,
        )
        self._manual_reassignment_proposals[proposal_id] = {
            "result": candidate_result,
            "task_id": task_id,
            "engineer_id": engineer_id,
        }
        return {
            "feasible": True,
            "proposal_id": proposal_id,
            "task_id": task_id,
            "old_engineer": (
                {"id": old_engineer.id, "name": old_engineer.name}
                if old_engineer else None
            ),
            "new_engineer": {"id": engineer.id, "name": engineer.name},
            "before": before,
            "after": after,
            "delta": {
                "used_engineers_count": (
                    after["used_engineers_count"] - before["used_engineers_count"]
                ),
                "total_distance_km": round(
                    after["total_distance_km"] - before["total_distance_km"], 3
                ),
            },
        }

    def confirm_manual_reassignment(
        self, proposal_id: str
    ) -> tuple[JsonScenario, OptimizationResult, dict[str, Any]]:
        """Применяет результат preview; повторный или устаревший ID не принимается."""
        proposal = self._manual_reassignment_proposals.get(proposal_id)
        if proposal is None or self._scenario is None:
            raise ValueError("Предложение переназначения не найдено или устарело")
        result: OptimizationResult = proposal["result"]
        assigned_by_task = {
            stop.task_id: engineer_id
            for engineer_id, route in result.routes.items()
            for stop in route.stops
        }
        tasks = []
        for task in self._scenario.tasks:
            if (
                not self._ignore_task_statuses
                and task.status in {TaskStatus.CANCELLED, TaskStatus.COMPLETED}
            ):
                tasks.append(task)
            elif (
                not self._ignore_task_statuses
                and task.status in {TaskStatus.EN_ROUTE, TaskStatus.IN_PROGRESS}
            ):
                tasks.append(task)
            elif task.id in assigned_by_task:
                tasks.append(
                    replace(
                        task,
                        status=TaskStatus.ASSIGNED,
                        current_engineer_id=assigned_by_task[task.id],
                    )
                )
            else:
                tasks.append(
                    replace(
                        task,
                        status=(
                            TaskStatus.OVERDUE
                            if task.status == TaskStatus.OVERDUE
                            else TaskStatus.NOT_SENT
                        ),
                        current_engineer_id=None,
                    )
                )
        self._scenario = replace(self._scenario, tasks=tuple(tasks))
        self._problem = replace(self._problem, tasks=tuple(tasks)) if self._problem else None
        self._result = result
        confirmation = {
            "proposal_id": proposal_id,
            "task_id": proposal["task_id"],
            "engineer_id": proposal["engineer_id"],
        }
        self._manual_reassignment_proposals.clear()
        return self._scenario, result, confirmation

    @staticmethod
    def _infeasible_reassignment(reason_code: str, message: str) -> dict[str, Any]:
        """Формирует единый структурированный ответ о невозможности переноса."""
        return {"feasible": False, "reason_code": reason_code, "message": message}

    @staticmethod
    def _main_metrics(result: OptimizationResult) -> dict[str, int | float]:
        """Возвращает две обязательные метрики ТЗ для окна подтверждения."""
        return {
            "used_engineers_count": result.used_engineers_count,
            "total_distance_km": round(result.total_distance, 3),
        }

    def replan_current(
        self,
        event: dict[str, Any],
    ) -> tuple[JsonScenario, OptimizationResult, dict[str, Any]]:
        """Применяет оперативное событие и перестраивает оставшийся план."""
        scenario = self.current_dataset()
        reference_routes = (
            {
                engineer_id: tuple(stop.task_id for stop in route.stops)
                for engineer_id, route in self._result.routes.items()
            }
            if self._result is not None
            else None
        )
        initial_routes = (
            dict(reference_routes) if reference_routes is not None else None
        )
        event_type = event["event_type"]
        details: dict[str, Any] = {"event_type": event_type}

        if event_type == "ENGINEER_UNAVAILABLE":
            engineer_id = event["engineer_id"]
            if engineer_id not in {engineer.id for engineer in scenario.engineers}:
                raise ValueError(f"Инженер {engineer_id!r} не найден")
            self._unavailable_engineer_ids.add(engineer_id)
            # Начатая работа больше не может оставаться жёстко закреплённой за
            # недоступным исполнителем. Она возвращается в очередь; COMPLETED
            # и CANCELLED сохраняются как история.
            tasks = tuple(
                replace(task, status=TaskStatus.NOT_SENT, current_engineer_id=None)
                if task.current_engineer_id == engineer_id
                and task.status in {
                    TaskStatus.ASSIGNED,
                    TaskStatus.EN_ROUTE,
                    TaskStatus.IN_PROGRESS,
                    TaskStatus.OVERDUE,
                }
                else task
                for task in scenario.tasks
            )
            scenario = replace(scenario, tasks=tasks)
            self._scenario = scenario
            if initial_routes is not None:
                initial_routes.pop(engineer_id, None)
            details["engineer_id"] = engineer_id

        elif event_type == "TASK_CANCELLED":
            task_id = event["task_id"]
            if not any(task.id == task_id for task in scenario.tasks):
                raise ValueError(f"Заявка {task_id!r} не найдена")
            scenario = replace(
                scenario,
                tasks=tuple(
                    replace(task, status=TaskStatus.CANCELLED, current_engineer_id=None)
                    if task.id == task_id
                    else task
                    for task in scenario.tasks
                ),
            )
            self._scenario = scenario
            # Удаляем только отменённую остановку из стартового снимка.
            # Остальные маршруты используются как начальное решение без
            # пересборки чужого порядка заявок.
            if initial_routes is not None:
                for engineer_id, route in initial_routes.items():
                    initial_routes[engineer_id] = tuple(
                        item for item in route if item != task_id
                    )
            if reference_routes is not None:
                for engineer_id, route in reference_routes.items():
                    reference_routes[engineer_id] = tuple(
                        item for item in route if item != task_id
                    )
            details["task_id"] = task_id

        elif event_type == "EMERGENCY_TASK":
            task_data = dict(event["task"])
            task_data["priority"] = Priority.URGENT.value
            task_data["work_type"] = WorkType.EMERGENCY.value
            task_data["status"] = TaskStatus.NOT_SENT.value
            scenario = self.add_task(task_data)
            details["task_id"] = task_data["id"]
        else:  # pragma: no cover — serializer ограничивает справочник.
            raise ValueError(f"Неизвестное событие {event_type!r}")

        # Во всех оперативных сценариях обычные ASSIGNED и NOT_SENT можно
        # перестраивать. EN_ROUTE/IN_PROGRESS остальных доступных инженеров
        # остаются жёстко закреплёнными правилами OptimizationProblem.
        # При недоступности инженера его активные заявки предварительно
        # переводятся в NOT_SENT: физически отсутствующий исполнитель не
        # может завершить даже уже начатую работу.
        self._problem = None
        self._result = None
        scenario, result = self.optimize_current(
            ignore_task_statuses=False,
            planning_time=event.get("planning_time"),
            initial_routes_by_engineer=initial_routes,
            reference_routes_by_engineer=reference_routes,
            preserve_assigned_tasks=False,
            consider_equipment=bool(
                event.get("consider_equipment", self._consider_equipment)
            ),
        )
        return scenario, result, details

    @staticmethod
    def _complete_operational_states(
        scenario: JsonScenario,
        planning_time: str | None,
        states: tuple[EngineerOperationalState, ...],
    ) -> tuple[EngineerOperationalState, ...]:
        """Дополняет снимок очевидной позицией уже работающего инженера."""
        if planning_time is None:
            return states
        by_engineer = {state.engineer_id: state for state in states}
        for task in scenario.tasks:
            if (
                task.status == TaskStatus.IN_PROGRESS
                and task.current_engineer_id is not None
                and task.current_engineer_id not in by_engineer
            ):
                by_engineer[task.current_engineer_id] = EngineerOperationalState(
                    engineer_id=task.current_engineer_id,
                    current_location_id=task.location_id,
                )
        return tuple(by_engineer.values())

    def add_task(self, data: dict[str, Any]) -> JsonScenario:
        """Добавляет валидированную заявку в текущий in-memory dataset."""
        scenario = self.current_dataset()
        task_id = data["id"].strip()
        if any(task.id == task_id for task in scenario.tasks):
            raise ValueError(f"Заявка {task_id!r} уже существует")
        location_id = f"task:{task_id}"
        norm = WORK_NORMS[WorkType(data["work_type"])]
        # Приоритет задаётся типом работ по ТЗ: авария всегда срочная,
        # остальные новые заявки имеют обычный приоритет.
        priority = (
            Priority.URGENT
            if WorkType(data["work_type"]) == WorkType.EMERGENCY
            else Priority.NORMAL
        )
        task = Task(
            id=task_id,
            location_id=location_id,
            required_skills=frozenset({norm.required_skill}),
            duration_minutes=norm.duration_minutes,
            window_start=data["window_start"],
            window_end=data["window_end"],
            work_type=WorkType(data["work_type"]),
            priority=priority,
            # Созданная диспетчером заявка ещё никому не отправлена.
            status=TaskStatus.NOT_SENT,
            required_router_count=data.get("required_router_count", 0),
            required_vehicle_type=(
                VehicleType(data["required_vehicle_type"])
                if data.get("required_vehicle_type")
                else None
            ),
            latitude=data["latitude"],
            longitude=data["longitude"],
            address=data.get("address", "").strip() or None,
        )
        self._register_late_day_manual_task(scenario, task)
        coordinates = dict(scenario.location_coordinates)
        new_coordinates = (task.latitude, task.longitude)
        if location_id in coordinates and coordinates[location_id] != new_coordinates:
            raise ValueError(
                f"Локация {location_id!r} уже существует с другими координатами"
            )
        coordinates[location_id] = new_coordinates
        self._scenario = replace(
            scenario,
            tasks=(*scenario.tasks, task),
            location_coordinates=coordinates,
        )
        self._problem = None
        if self._result is not None:
            # После появления новой заявки текущий маршрут остаётся рабочим.
            # Следующий запуск solver фиксирует эти назначения и добавляет
            # только NOT_SENT-заявки.
            self._ignore_task_statuses = False
            self._preserve_assigned_tasks = True
        self._manual_reassignment_proposals.clear()
        # Старый provider ещё нужен в этом ответе для geometry сохранённых
        # маршрутов. Перед следующим расчётом он будет построен заново уже с
        # координатой новой заявки.
        self._routing_provider_requires_rebuild = True
        return self._scenario

    @staticmethod
    def _is_late_day(scenario: JsonScenario) -> bool:
        """Определяет наступление условных 14:00 по фактическим статусам."""
        return any(
            task.window_start >= "14:00"
            and task.status in {TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED}
            for task in scenario.tasks
        )

    def _register_late_day_manual_task(
        self,
        scenario: JsonScenario,
        task: Task,
    ) -> None:
        """Запоминает доступный после 14:00 состав инженеров на линии."""
        # Авария является форс-мажором и может потребовать вызова ещё одной
        # бригады; запрет применяется только к обычным ручным заявкам.
        if task.work_type == WorkType.EMERGENCY:
            return
        if not self._late_day_manual_task_ids and not self._is_late_day(scenario):
            return
        if not self._late_day_manual_task_ids:
            active_engineers = {
                engineer_id
                for engineer_id, route in (
                    self._result.routes.items() if self._result is not None else ()
                )
                if route.stops
            }
            active_engineers.update(
                item.current_engineer_id
                for item in scenario.tasks
                if item.current_engineer_id is not None
                and item.status
                in {
                    TaskStatus.ASSIGNED,
                    TaskStatus.EN_ROUTE,
                    TaskStatus.IN_PROGRESS,
                    TaskStatus.COMPLETED,
                }
            )
            self._late_day_active_engineer_ids = active_engineers
        self._late_day_manual_task_ids.add(task.id)

    def _validate_late_day_engineer_activation(
        self,
        scenario: JsonScenario,
        result: OptimizationResult,
    ) -> None:
        """Отклоняет план, вызывающий после 14:00 нового инженера из дома."""
        if not self._late_day_manual_task_ids:
            return
        used_engineer_ids = {
            engineer_id
            for engineer_id, route in result.routes.items()
            if route.stops
        }
        newly_activated = used_engineer_ids - self._late_day_active_engineer_ids
        if not newly_activated:
            return
        engineers_by_id = {item.id: item for item in scenario.engineers}
        names = ", ".join(
            engineers_by_id[engineer_id].name
            for engineer_id in sorted(newly_activated)
        )
        task_ids = ", ".join(sorted(self._late_day_manual_task_ids))
        raise ValueError(
            "После условных 14:00 нельзя вызывать на линию нового инженера "
            f"для вручную созданных заявок {task_ids}. Новый план потребовал "
            f"бы инженеров: {names}. План отклонён; заявки остаются не назначены."
        )

    def geocode_address(self, address: str) -> tuple[float, float]:
        """Находит точный адрес через локальный или публичный Nominatim."""
        if self._geocoder is None:
            cache_path = Path(__file__).resolve().parents[3] / ".cache" / "nominatim_web.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._geocoder = NominatimGeocoder(
                cache_path=cache_path,
                allow_street_fallback=False,
            )
        reference_coordinates = None
        if (
            self._scenario is not None
            and self._scenario.office_latitude is not None
            and self._scenario.office_longitude is not None
        ):
            reference_coordinates = (
                self._scenario.office_latitude,
                self._scenario.office_longitude,
            )
        return self._geocoder(
            address,
            reference_coordinates=reference_coordinates,
        )

    def explain_current_task(self, task_id: str) -> tuple[dict[str, Any], str]:
        """Строит decision trace и получает его объяснение от LLM."""
        if self._problem is None or self._result is None:
            raise ValueError("Сначала запустите оптимизацию")
        trace = ExplanationEngine().explain_task(
            self._problem,
            self._result,
            task_id,
        )
        # LLM остаётся отдельным слоем: математическое ядро формирует только
        # проверяемые факты, а этот сервис передаёт их внешнему адаптеру.
        from LLM.query import explain_assignment

        try:
            explanation = explain_assignment(trace)
        except Exception:  # noqa: BLE001: внешний LLM может быть временно недоступен.
            # Проверяемые причины уже сформированы математическим ядром. Даже
            # если ключ GigaChat не настроен или внешний API недоступен, UI
            # должен показать этот JSON, а не скрывать результат проверки.
            explanation = (
                "Текстовое объяснение LLM временно недоступно."
            )
        return trace, explanation.strip()

    def _build_problem(
        self,
        scenario: JsonScenario,
        *,
        planning_time: str | None = None,
        operational_states: tuple[EngineerOperationalState, ...] = (),
    ) -> OptimizationProblem:
        """Добавляет к импортированным сущностям routing data.

        В обычном web-запуске используется OSRM. Тесты переключают
        ``use_osrm`` в ``False`` и получают воспроизводимую локальную матрицу.
        """
        if self.routing_provider is not None and not self._routing_provider_requires_rebuild:
            provider = self.routing_provider
        elif self.use_osrm:
            provider = create_osrm_provider_from_environment(
                coordinates=scenario.location_coordinates,
                request_timeout_seconds=float(
                    os.getenv("OSRM_TIMEOUT_SECONDS", "15")
                ),
            )
        else:
            provider = CoordinateRoutingProvider(
                coordinates=scenario.location_coordinates,
                speed_km_per_hour=30.0,
            )
        self.routing_provider = provider
        self._routing_provider_requires_rebuild = False
        vehicle_types = tuple(
            dict.fromkeys(engineer.vehicle_type for engineer in scenario.engineers)
        )
        return scenario.to_problem(
            provider,
            vehicle_types=vehicle_types,
            preserve_assigned_tasks=self._preserve_assigned_tasks,
            ignore_task_statuses=self._ignore_task_statuses,
            planning_time=planning_time,
            operational_states=operational_states,
            unavailable_engineer_ids=self._unavailable_engineer_ids,
            consider_equipment=getattr(self, "_consider_equipment", False),
        )

    def serialize_dataset(self, scenario: JsonScenario) -> dict[str, Any]:
        """Сериализует dataset для Vue-таблиц и карты."""
        serializer = DatasetSerializer(
            instance=scenario,
            context={
                "source_name": self._source_name,
                "preserve_assigned_tasks": self._preserve_assigned_tasks,
                "ignore_task_statuses": self._ignore_task_statuses,
                # Контрольные статусы становятся видимыми только после
                # построения результата. При первичной загрузке JSON это
                # всего лишь исходные данные для будущего расчёта.
                "has_plan": self._result is not None,
            },
        )

        return dict(serializer.data)

    def serialize_response(
        self,
        scenario: JsonScenario,
        result: OptimizationResult | None = None,
    ) -> dict[str, Any]:
        """Возвращает dataset и, если есть, результат оптимизации."""
        response: dict[str, Any] = {"dataset": self.serialize_dataset(scenario)}
        if result is not None:
            response["result"] = self._serialize_result(scenario, result)
        return response

    # def _serialize_result(
    #     self,
    #     scenario: JsonScenario,
    #     result: OptimizationResult,
    # ) -> dict[str, Any]:
    #     """Преобразует маршруты и метрики OptimizationResult в JSON."""
    #     engineers_by_id = {engineer.id: engineer for engineer in scenario.engineers}
    #     tasks_by_id = {task.id: task for task in scenario.tasks}
    #     routes = []
    #     for engineer_id, route in result.routes.items():
    #         engineer = engineers_by_id[engineer_id]
    #         route_location_ids = [engineer.start_location_id] + [
    #             tasks_by_id[stop.task_id].location_id for stop in route.stops
    #         ]
    #         geometry = (
    #             self.routing_provider.get_route_geometry(
    #                 route_location_ids,
    #                 engineer.vehicle_type,
    #             )
    #             if self.routing_provider is not None
    #             else None
    #         )
    #         routes.append(
    #             {
    #                 "engineer_id": engineer_id,
    #                 "engineer_name": engineer.name,
    #                 "vehicle_type": engineer.vehicle_type.value,
    #                 "start_latitude": engineer.start_latitude,
    #                 "start_longitude": engineer.start_longitude,
    #                 "total_distance_km": route.total_distance_km,
    #                 "total_travel_minutes": route.total_travel_minutes,
    #                 "geometry": geometry,
    #                 "stops": [
    #                     {
    #                         "task_id": stop.task_id,
    #                         "latitude": tasks_by_id[stop.task_id].latitude,
    #                         "longitude": tasks_by_id[stop.task_id].longitude,
    #                         "arrival_time": stop.arrival_time,
    #                         "service_start_time": stop.service_start_time,
    #                         "service_end_time": stop.service_end_time,
    #                         "travel_time_from_previous": stop.travel_time_from_previous,
    #                         "distance_from_previous_km": stop.distance_from_previous_km,
    #                     }
    #                     for stop in route.stops
    #                 ],
    #             }
    #         )
    #     return {
    #         "metrics": {
    #             "assigned_task_count": result.assigned_task_count,
    #             "unassigned_task_count": result.unassigned_task_count,
    #             "used_engineers_count": result.used_engineers_count,
    #             "total_distance_km": result.total_distance,
    #             "total_travel_minutes": result.total_travel_time,
    #             "total_objective": result.total_objective,
    #             "unassigned_penalty": result.unassigned_penalty,
    #             "used_engineers_penalty": result.used_engineers_penalty,
    #             "distance_penalty": result.distance_penalty,
    #             "travel_time_penalty": result.travel_time_penalty,
    #         },
    #         "distance_by_engineer": result.distance_by_engineer,
    #         "travel_time_by_engineer": result.travel_time_by_engineer,
    #         "routes": routes,
    #         "unassigned": [
    #             {
    #                 "task_id": task_id,
    #                 "reason_code": reason.code.value,
    #                 "message": reason.message,
    #             }
    #             for task_id, reason in result.unassigned_reasons.items()
    #         ],
    #     }

    def _serialize_result(
        self,
        scenario: JsonScenario,
        result: OptimizationResult,
    ) -> dict[str, Any]:
        """Преобразует маршруты и метрики OptimizationResult в JSON."""

        serializer = OptimizationResultSerializer(
            result,
            context={
                "scenario": scenario,
                "routing_provider": self.routing_provider,
                "problem": self._problem,
            }
        )
        return serializer.data
