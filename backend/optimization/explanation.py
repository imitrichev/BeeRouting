"""Формирование проверяемых фактов для объяснения маршрутов.

Модуль не генерирует русский текст и не принимает решений вместо solver. Он
готовит JSON-факты для LLM и frontend:

1. быстрые проверки hard constraints и вставки заявки в существующие маршруты;
2. короткий counterfactual-запуск OR-Tools для допустимых кандидатов.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .config import OptimizerConfig
from .models import (
    Engineer,
    OptimizationProblem,
    OptimizationResult,
    Task,
    TaskStatus,
    hhmm_to_minutes,
)
from .ortools_optimizer import ORToolsOptimizer


class ExplanationEngine:
    """Строит JSON-представление причин назначения или неназначения заявки."""

    def __init__(
        self,
        optimizer: ORToolsOptimizer | None = None,
        config: OptimizerConfig | None = None,
    ) -> None:
        """Создаёт слой объяснений с теми же параметрами, что и solver."""
        self.config = config or OptimizerConfig()
        self.optimizer = optimizer or ORToolsOptimizer(self.config)

    def explain_task(
        self,
        problem: OptimizationProblem,
        result: OptimizationResult,
        task_id: str,
    ) -> dict[str, Any]:
        """Возвращает decision trace для одной заявки.

        Counterfactual-запуски выполняются только для инженеров, которые прошли
        быструю проверку. Поэтому отсутствие навыка или оборудования не тратит
        время OR-Tools.
        """
        task = next((item for item in problem.tasks if item.id == task_id), None)
        if task is None:
            raise ValueError(f"Заявка {task_id!r} не найдена")

        engineers_by_id = {engineer.id: engineer for engineer in problem.engineers}
        tasks_by_id = {item.id: item for item in problem.tasks}
        assigned_engineer_id = self._assigned_engineer_id(result, task_id)
        assigned_engineer = engineers_by_id.get(assigned_engineer_id)
        routes = {
            engineer_id: [stop.task_id for stop in route.stops]
            for engineer_id, route in result.routes.items()
        }

        assessments: list[dict[str, Any]] = []
        for engineer in problem.engineers:
            hard_reasons = self._hard_reasons(problem, engineer, task)
            if (
                task.status
                in {
                    TaskStatus.CANCELLED,
                    TaskStatus.COMPLETED,
                    TaskStatus.EN_ROUTE,
                    TaskStatus.IN_PROGRESS,
                }
                and assigned_engineer_id is not None
                and engineer.id != assigned_engineer_id
            ):
                hard_reasons.append(
                    {
                        "event_type": "HARD_CONSTRAINT",
                        "code": "TASK_STATUS_LOCKED",
                        "message": (
                            f"Статус {task.status.value} запрещает перенос заявки "
                            "другому инженеру."
                        ),
                        "must_mention": True,
                    }
                )
            candidate_routes = {
                engineer_id: list(task_ids)
                for engineer_id, task_ids in routes.items()
            }
            if assigned_engineer_id is not None:
                candidate_routes[assigned_engineer_id] = [
                    item_id
                    for item_id in candidate_routes[assigned_engineer_id]
                    if item_id != task_id
                ]
            candidate_routes.setdefault(engineer.id, [])
            insertion = None
            if not hard_reasons:
                insertion = self._find_feasible_insertion(
                    problem,
                    engineer,
                    task,
                    candidate_routes[engineer.id],
                    tasks_by_id,
                )
                if insertion is None:
                    hard_reasons.extend(
                        self._route_failure_reasons(
                            problem,
                            engineer,
                            task,
                            candidate_routes[engineer.id],
                            tasks_by_id,
                        )
                    )

            assessment: dict[str, Any] = {
                "event_type": "candidate_assessment",
                "engineer": {
                    "id": engineer.id,
                    "name": engineer.name,
                    "vehicle_type": engineer.vehicle_type.value,
                    "qualifications": sorted(
                        skill.value for skill in engineer.qualifications
                    ),
                },
                "is_current_assignment": engineer.id == assigned_engineer_id,
                "feasible_after_stage_1": not hard_reasons and insertion is not None,
                "hard_reasons": hard_reasons,
                "must_mention": bool(hard_reasons),
                "route_before_candidate": candidate_routes[engineer.id],
            }
            if insertion is None:
                assessments.append(assessment)
                continue

            candidate_routes[engineer.id] = insertion["task_ids"]
            assessment["stage_1"] = {
                "event_type": "deterministic_insertion_check",
                "must_mention": False,
                "route_after_insertion": insertion["task_ids"],
                "travel_time_minutes": insertion["travel_time_minutes"],
                "distance_km": insertion["distance_km"],
                "insert_position": insertion["insert_position"],
            }

            if engineer.id != assigned_engineer_id:
                assessment["stage_2"] = self._counterfactual_check(
                    problem,
                    result,
                    task,
                    engineer,
                    candidate_routes,
                )
            else:
                assessment["stage_2"] = {
                    "event_type": "current_solution",
                    "status": "current_assignment",
                    "distance_delta_km": 0.0,
                    "travel_time_delta_minutes": 0,
                    "objective_delta": 0,
                    "must_mention": False,
                }
            stage_2 = assessment["stage_2"]
            assessment["impact"] = self._impact(
                stage_2.get("distance_delta_km"),
                stage_2.get("travel_time_delta_minutes"),
                stage_2.get("objective_delta"),
                stage_2.get("current_used_engineers_count"),
                stage_2.get("alternative_used_engineers_count"),
            )
            assessments.append(assessment)

        unassigned_reason = result.unassigned_reasons.get(task_id)
        assignment_reasons = self._assignment_reasons(
            task,
            assigned_engineer,
            assessments,
        )
        trace: dict[str, Any] = {
            "schema_version": "1.0",
            "event_type": "task_assignment_explanation",
            "task": {
                "id": task.id,
                "required_skill": next(iter(task.required_skills)).value,
                "required_equipment": sorted(task.required_equipment),
                "required_vehicle_type": (
                    task.required_vehicle_type.value
                    if task.required_vehicle_type is not None
                    else None
                ),
                "window_start": task.window_start,
                "window_end": task.window_end,
                "duration_minutes": task.duration_minutes,
                "priority": task.priority.value,
            },
            "assignment": {
                "status": "assigned" if assigned_engineer_id else "unassigned",
                "engineer": (
                    {
                        "id": assigned_engineer.id,
                        "name": assigned_engineer.name,
                        "vehicle_type": assigned_engineer.vehicle_type.value,
                    }
                    if assigned_engineer is not None
                    else None
                ),
            },
            "assignment_reasons": assignment_reasons,
            "unassigned_reason": (
                {
                    "event_type": "UNASSIGNED_REASON",
                    "code": unassigned_reason.code.value,
                    "message": unassigned_reason.message,
                    "must_mention": True,
                }
                if unassigned_reason is not None
                else None
            ),
            "checks": assessments,
            "explanation_policy": {
                "distance_threshold_km": self.config.explanation_distance_threshold_km,
                "travel_time_threshold_minutes": self.config.explanation_travel_time_threshold_minutes,
                "free_reassignments": self.config.explanation_free_reassignments,
                "reassignment_penalty": self.config.explanation_reassignment_penalty,
            },
        }
        return trace

    @staticmethod
    def _assignment_reasons(
        task: Task,
        assigned_engineer: Engineer | None,
        assessments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Выделяет только существенные причины назначения выбранному инженеру."""
        if assigned_engineer is None:
            return []
        feasible = [
            item
            for item in assessments
            if item["feasible_after_stage_1"]
        ]
        reasons: list[dict[str, Any]] = []
        required_skill = next(iter(task.required_skills)).value
        skill_candidates = [
            item
            for item in assessments
            if required_skill in item["engineer"]["qualifications"]
        ]
        if len(skill_candidates) == 1 and skill_candidates[0]["engineer"]["id"] == assigned_engineer.id:
            reasons.append(
                {
                    "event_type": "ASSIGNMENT_REASON",
                    "type": "ONLY_ENGINEER_WITH_REQUIRED_SKILL",
                    "message": "Только у выбранного инженера есть требуемая квалификация.",
                    "must_mention": True,
                }
            )
        # Кандидаты, прошедшие stage 1, уже удовлетворяют всем hard checks.
        # Если среди них остался только выбранный инженер, причина ещё шире:
        # другие инженеры не проходят хотя бы одну жёсткую проверку.
        if len(feasible) == 1 and feasible[0]["engineer"]["id"] == assigned_engineer.id and not reasons:
            reasons.append(
                {
                    "event_type": "ASSIGNMENT_REASON",
                    "type": "ONLY_FEASIBLE_ENGINEER",
                    "message": "Только выбранный инженер проходит все жёсткие проверки.",
                    "must_mention": True,
                }
            )
        return reasons

    @staticmethod
    def _assigned_engineer_id(result: OptimizationResult, task_id: str) -> str | None:
        """Находит инженера, в чей маршрут попала заявка."""
        for engineer_id, route in result.routes.items():
            if any(stop.task_id == task_id for stop in route.stops):
                return engineer_id
        return None

    @staticmethod
    def _hard_reasons(
        problem: OptimizationProblem,
        engineer: Engineer,
        task: Task,
    ) -> list[dict[str, Any]]:
        """Возвращает понятные причины невозможности назначения инженеру."""
        reasons: list[dict[str, Any]] = []
        missing_skills = task.required_skills - engineer.qualifications
        if missing_skills:
            reasons.append(
                {
                    "event_type": "HARD_CONSTRAINT_FAILURE",
                    "type": "MISSING_SKILL",
                    "message": "У инженера нет требуемой квалификации.",
                    "missing_skills": sorted(skill.value for skill in missing_skills),
                    "must_mention": True,
                }
            )

        equipment_by_id = {item.id: item for item in problem.equipment_resources}
        equipment = set(engineer.available_equipment)
        equipment.update(
            equipment_by_id[resource_id].equipment_type
            for resource_id in engineer.equipment_resource_ids
            if resource_id in equipment_by_id
        )
        missing_equipment = task.required_equipment - equipment
        if missing_equipment:
            reasons.append(
                {
                    "event_type": "HARD_CONSTRAINT_FAILURE",
                    "type": "MISSING_EQUIPMENT",
                    "message": "У инженера нет требуемого оборудования.",
                    "missing_equipment": sorted(missing_equipment),
                    "must_mention": True,
                }
            )
        if (
            problem.consider_equipment
            and task.required_router_count > problem.available_router_count_for_planning(engineer)
        ):
            reasons.append(
                {
                    "event_type": "HARD_CONSTRAINT_FAILURE",
                    "type": "MISSING_EQUIPMENT",
                    "message": "У инженера недостаточно роутеров.",
                    "required_router_count": task.required_router_count,
                    "available_router_count": problem.available_router_count_for_planning(engineer),
                    "must_mention": True,
                }
            )

        actual_vehicle = engineer.vehicle_type
        if engineer.vehicle_resource_id is not None:
            vehicle_by_id = {item.id: item for item in problem.vehicle_resources}
            resource = vehicle_by_id.get(engineer.vehicle_resource_id)
            if resource is not None:
                actual_vehicle = resource.vehicle_type
        if task.required_vehicle_type is not None and actual_vehicle != task.required_vehicle_type:
            reasons.append(
                {
                    "event_type": "HARD_CONSTRAINT_FAILURE",
                    "type": "MISMATCHED_VEHICLE",
                    "message": "Тип транспорта инженера не соответствует заявке.",
                    "required_vehicle_type": task.required_vehicle_type.value,
                    "engineer_vehicle_type": actual_vehicle.value,
                    "must_mention": True,
                }
            )
        return reasons

    def _find_feasible_insertion(
        self,
        problem: OptimizationProblem,
        engineer: Engineer,
        task: Task,
        route_task_ids: list[str],
        tasks_by_id: dict[str, Task],
    ) -> dict[str, Any] | None:
        """Ищет первую допустимую позицию заявки в маршруте инженера."""
        for position in range(len(route_task_ids) + 1):
            candidate_ids = [
                *route_task_ids[:position],
                task.id,
                *route_task_ids[position:],
            ]
            simulation = self._simulate_route(
                problem,
                engineer,
                [tasks_by_id[item_id] for item_id in candidate_ids],
            )
            if simulation["feasible"]:
                return {
                    "task_ids": candidate_ids,
                    "insert_position": position,
                    "travel_time_minutes": simulation["travel_time_minutes"],
                    "distance_km": simulation["distance_km"],
                }
        return None

    def _route_failure_reasons(
        self,
        problem: OptimizationProblem,
        engineer: Engineer,
        task: Task,
        route_task_ids: list[str],
        tasks_by_id: dict[str, Task],
    ) -> list[dict[str, Any]]:
        """Определяет причину отказа после прохождения hard-проверок."""
        single = self._simulate_route(problem, engineer, [task])
        if single["failure_type"] == "window":
            return [{
                "event_type": "HARD_CONSTRAINT_FAILURE",
                "type": "IMPOSSIBLE_TIME_WINDOW",
                "message": single["message"],
                "must_mention": True,
            }]
        if single["failure_type"] == "shift":
            return [{
                "event_type": "HARD_CONSTRAINT_FAILURE",
                "type": "OUTSIDE_WORKING_HOURS",
                "message": single["message"],
                "must_mention": True,
            }]
        if single["failure_type"] == "equipment":
            return [{
                "event_type": "HARD_CONSTRAINT_FAILURE",
                "type": "MISSING_EQUIPMENT",
                "message": single["message"],
                "must_mention": True,
            }]
        trial = self._simulate_route(
            problem,
            engineer,
            [tasks_by_id[item_id] for item_id in route_task_ids],
        )
        return [
            {
                "event_type": "HARD_CONSTRAINT_FAILURE",
                "type": "ROUTE_CONFLICT",
                "message": "Заявку нельзя вставить в текущий маршрут без нарушения окна или смены.",
                "blocking_task_ids": trial["blocking_task_ids"],
                "must_mention": True,
            }
        ]

    @staticmethod
    def _simulate_route(
        problem: OptimizationProblem,
        engineer: Engineer,
        tasks: list[Task],
    ) -> dict[str, Any]:
        """Проверяет порядок заявок без запуска solver."""
        availability = next(
            item for item in problem.availabilities if item.engineer_id == engineer.id
        )
        current_time = hhmm_to_minutes(availability.available_from)
        shift_end = hhmm_to_minutes(availability.available_until)
        previous_location = engineer.start_location_id
        travel_time = 0
        distance = 0.0
        blocking_task_ids: list[str] = []
        routers_used = 0
        for task in tasks:
            if problem.consider_equipment:
                routers_used += task.required_router_count
                available_routers = problem.available_router_count_for_planning(engineer)
                if routers_used > available_routers:
                    return {
                        "feasible": False,
                        "failure_type": "equipment",
                        "message": f"Для маршрута требуется {routers_used} роутеров, "
                        f"а у инженера доступно {available_routers}.",
                        "blocking_task_ids": blocking_task_ids,
                        "travel_time_minutes": travel_time,
                        "distance_km": distance,
                    }
            travel = problem.travel_time_between(
                previous_location,
                task.location_id,
                engineer.vehicle_type,
            )
            distance += problem.travel_distance_between(
                previous_location,
                task.location_id,
                engineer.vehicle_type,
            )
            travel_time += travel
            arrival = current_time + travel
            service_start = max(arrival, hhmm_to_minutes(task.window_start))
            if service_start > hhmm_to_minutes(task.window_end):
                return {
                    "feasible": False,
                    "failure_type": "window",
                    "message": f"После маршрута инженер прибывает после окна {task.window_start}–{task.window_end}.",
                    "blocking_task_ids": blocking_task_ids,
                    "travel_time_minutes": travel_time,
                    "distance_km": distance,
                }
            service_end = service_start + task.duration_minutes
            if service_end > shift_end:
                return {
                    "feasible": False,
                    "failure_type": "shift",
                    "message": f"Работа заканчивается после смены инженера {availability.available_until}.",
                    "blocking_task_ids": blocking_task_ids,
                    "travel_time_minutes": travel_time,
                    "distance_km": distance,
                }
            current_time = service_end
            previous_location = task.location_id
            blocking_task_ids.append(task.id)
        return {
            "feasible": True,
            "failure_type": None,
            "message": "",
            "blocking_task_ids": blocking_task_ids,
            "travel_time_minutes": travel_time,
            "distance_km": distance,
        }

    def _counterfactual_check(
        self,
        problem: OptimizationProblem,
        current_result: OptimizationResult,
        task: Task,
        engineer: Engineer,
        initial_routes: dict[str, list[str]],
    ) -> dict[str, Any]:
        """Пересчитывает допустимую альтернативу коротким OR-Tools запуском."""
        current_routes = {
            engineer_id: tuple(stop.task_id for stop in route.stops)
            for engineer_id, route in current_result.routes.items()
        }
        current_engineer_by_task = {
            task_id: engineer_id
            for engineer_id, task_ids in current_routes.items()
            for task_id in task_ids
        }
        # Закрытые и уже выполняемые работы не должны «переезжать» между
        # инженерами во время объясняющего расчёта, даже если основной план
        # был построен в демонстрационном режиме игнорирования статусов.
        frozen_statuses = {
            "CANCELLED",
            "COMPLETED",
            "EN_ROUTE",
            "IN_PROGRESS",
        }
        forced_assignments = {
            item.id: current_engineer_by_task[item.id]
            for item in problem.tasks
            if item.status.value in frozen_statuses
            and item.id in current_engineer_by_task
        }
        forced_assignments[task.id] = engineer.id

        # Для объяснений цена переноса существенно ниже рабочего штрафа
        # перепланирования: 300 баллов соответствуют примерно 3 км. Изменение
        # порядка отдельно не штрафуется, поскольку диспетчеру важнее число
        # заявок, сменивших исполнителя.
        counterfactual_config = replace(
            self.config,
            reassignment_penalty=self.config.explanation_reassignment_penalty,
            route_order_change_penalty=0,
        )
        counterfactual_optimizer = ORToolsOptimizer(counterfactual_config)
        try:
            alternative = counterfactual_optimizer.optimize(
                problem,
                forced_task_engineer_by_id=forced_assignments,
                initial_routes_by_engineer=initial_routes,
                reference_routes_by_engineer=current_routes,
                time_limit_seconds=self.config.explanation_time_limit_seconds,
            )
        except (ValueError, KeyError) as exc:
            return {
                "event_type": "counterfactual_optimization",
                "status": "failed",
                "message": str(exc),
                "must_mention": False,
            }

        assigned = any(
            stop.task_id == task.id
            for route in alternative.routes.values()
            for stop in route.stops
        )
        if not assigned:
            return {
                "event_type": "counterfactual_optimization",
                "status": "infeasible",
                "message": "Короткий counterfactual-расчёт не нашёл допустимый план.",
                "must_mention": False,
            }
        distance_delta = alternative.total_distance - current_result.total_distance
        travel_delta = alternative.total_travel_time - current_result.total_travel_time
        # Первые два переноса считаются допустимой локальной корректировкой.
        # OR-Tools во время поиска начисляет 300 за каждый перенос; здесь
        # вычитаем бесплатный порог из итоговой декомпозиции.
        charged_reassignments = max(
            0,
            alternative.reassigned_task_count
            - self.config.explanation_free_reassignments,
        )
        plan_disruption_penalty = (
            self.config.explanation_plan_disruption_penalty(
                alternative.reassigned_task_count
            )
        )
        current_core_objective = self._core_objective(current_result)
        alternative_core_objective = self._core_objective(alternative)
        alternative_objective = alternative_core_objective + plan_disruption_penalty
        objective_delta = alternative_objective - current_core_objective
        current_engineer_id = self._assigned_engineer_id(
            current_result,
            task.id,
        )
        current_engineer_distance = (
            current_result.distance_by_engineer.get(current_engineer_id, 0.0)
            if current_engineer_id is not None
            else 0.0
        )
        alternative_engineer_distance = alternative.distance_by_engineer.get(
            engineer.id,
            0.0,
        )
        current_engineer_travel_time = (
            current_result.travel_time_by_engineer.get(current_engineer_id, 0)
            if current_engineer_id is not None
            else 0
        )
        alternative_engineer_travel_time = alternative.travel_time_by_engineer.get(
            engineer.id,
            0,
        )
        return {
            "event_type": "counterfactual_optimization",
            "status": "feasible",
            "distance_delta_km": round(distance_delta, 3),
            "travel_time_delta_minutes": travel_delta,
            "objective_delta": objective_delta,
            "current_assigned_engineer_id": current_engineer_id,
            "current_assigned_engineer_distance_km": round(
                current_engineer_distance,
                3,
            ),
            "alternative_engineer_distance_km": round(
                alternative_engineer_distance,
                3,
            ),
            "current_assigned_engineer_travel_time_minutes": current_engineer_travel_time,
            "alternative_engineer_travel_time_minutes": alternative_engineer_travel_time,
            "alternative_total_distance_km": round(alternative.total_distance, 3),
            "alternative_total_travel_time_minutes": alternative.total_travel_time,
            # Эти поля повторяют ту же декомпозицию, которую ORToolsOptimizer
            # использует при сборке OptimizationResult. Благодаря этому LLM
            # видит цену нового маршрута, а не только выигрыш по расстоянию.
            "current_used_engineers_count": current_result.used_engineers_count,
            "alternative_used_engineers_count": alternative.used_engineers_count,
            "reassigned_task_count": alternative.reassigned_task_count,
            "free_reassignments_count": self.config.explanation_free_reassignments,
            "charged_reassignments_count": charged_reassignments,
            "objective": {
                "current": self._objective_components(
                    current_result,
                    plan_disruption_penalty=0,
                    total_objective=current_core_objective,
                ),
                "alternative": self._objective_components(
                    alternative,
                    plan_disruption_penalty=plan_disruption_penalty,
                    total_objective=alternative_objective,
                ),
                "delta": {
                    "unassigned_penalty": alternative.unassigned_penalty
                    - current_result.unassigned_penalty,
                    "used_engineers_penalty": alternative.used_engineers_penalty
                    - current_result.used_engineers_penalty,
                    "distance_penalty": alternative.distance_penalty
                    - current_result.distance_penalty,
                    "travel_time_penalty": alternative.travel_time_penalty
                    - current_result.travel_time_penalty,
                    "plan_disruption_penalty": plan_disruption_penalty,
                    "total_objective": objective_delta,
                },
            },
            "must_mention": (
                objective_delta < 0
                and (
                    abs(distance_delta) >= self.config.explanation_distance_threshold_km
                    or abs(travel_delta) >= self.config.explanation_travel_time_threshold_minutes
                    or alternative.used_engineers_count != current_result.used_engineers_count
                    or alternative.reassigned_task_count > 0
                )
            ),
        }

    @staticmethod
    def _core_objective(result: OptimizationResult) -> int:
        """Возвращает objective маршрута без штрафа относительно старого плана."""
        return (
            result.unassigned_penalty
            + result.used_engineers_penalty
            + result.distance_penalty
            + result.travel_time_penalty
        )

    @staticmethod
    def _objective_components(
        result: OptimizationResult,
        *,
        plan_disruption_penalty: int,
        total_objective: int,
    ) -> dict[str, int]:
        """Возвращает полную декомпозицию objective объясняющего расчёта."""
        return {
            "unassigned_penalty": result.unassigned_penalty,
            "used_engineers_penalty": result.used_engineers_penalty,
            "distance_penalty": result.distance_penalty,
            "travel_time_penalty": result.travel_time_penalty,
            "plan_disruption_penalty": plan_disruption_penalty,
            "total_objective": total_objective,
        }

    def _impact(
        self,
        distance_delta: Any,
        travel_delta: Any,
        objective_delta: Any,
        current_used_engineers_count: Any,
        alternative_used_engineers_count: Any,
    ) -> dict[str, Any] | None:
        """Формирует отдельное событие влияния альтернативы."""
        if distance_delta is None or travel_delta is None:
            return None
        used_engineers_changed = (
            current_used_engineers_count is not None
            and alternative_used_engineers_count is not None
            and current_used_engineers_count != alternative_used_engineers_count
        )
        if not (
            abs(distance_delta) >= self.config.explanation_distance_threshold_km
            or abs(travel_delta) >= self.config.explanation_travel_time_threshold_minutes
            or used_engineers_changed
        ):
            return None
        if objective_delta < 0:
            direction = "better"
        elif objective_delta > 0:
            direction = "worse"
        else:
            direction = "same"
        # Ухудшающие альтернативы доступны разработчику в stage_2, но не
        # должны отвлекать диспетчера отдельной рекомендацией.
        if direction != "better":
            return None
        return {
            "event_type": "OBJECTIVE_IMPACT",
            "distance_difference_km": round(distance_delta, 3),
            "travel_time_difference_min": travel_delta,
            "objective_difference": objective_delta,
            "used_engineers_difference": (
                alternative_used_engineers_count - current_used_engineers_count
                if used_engineers_changed
                else 0
            ),
            "direction": direction,
            "must_mention": True,
        }
