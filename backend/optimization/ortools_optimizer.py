"""Реализация маршрутизации на базе Google OR-Tools."""

from __future__ import annotations

from datetime import timedelta
import math
from typing import Any

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .config import OptimizerConfig
from .interfaces import RouteOptimizer
from .models import (
    Engineer,
    EngineerRoute,
    OptimizationProblem,
    OptimizationResult,
    RouteStop,
    Task,
    UnassignedReason,
    UnassignedReasonCode,
    hhmm_to_minutes,
    minutes_to_hhmm,
)


class ORToolsOptimizer(RouteOptimizer):
    """Решатель VRP с жёсткими ограничениями доменной модели."""

    def __init__(self, config: OptimizerConfig | None = None) -> None:
        """Создаёт решатель с переданной или стандартной конфигурацией."""
        self.config = config or OptimizerConfig()

    def optimize(self, problem: OptimizationProblem) -> OptimizationResult:
        """Определяет назначения, порядок заявок и расписание маршрутов."""
        eligible_tasks: list[Task] = []
        unassigned_reasons: dict[str, UnassignedReason] = {}
        for task in problem.tasks:
            if self._has_eligible_engineer(problem, task):
                eligible_tasks.append(task)
            else:
                unassigned_reasons[task.id] = self._eligibility_unassigned_reason(
                    problem, task
                )

        if not eligible_tasks:
            return self._build_result(
                problem=problem,
                routes=self._empty_routes(problem),
                unassigned_reasons=unassigned_reasons,
                total_travel_minutes=0,
                total_distance_km=0.0,
            )

        engineer_count = len(problem.engineers)
        node_location_ids = [
            engineer.start_location_id for engineer in problem.engineers
        ] + [task.location_id for task in eligible_tasks]
        task_by_node = {
            engineer_count + task_index: task
            for task_index, task in enumerate(eligible_tasks)
        }
        task_node_by_id = {
            task.id: task_node for task_node, task in task_by_node.items()
        }
        starts = list(range(engineer_count))
        # OR-Tools называет каждый маршрут vehicle. В нашем домене один такой
        # маршрут соответствует одному инженеру; это не физический автомобиль.
        manager = pywrapcp.RoutingIndexManager(
            len(node_location_ids),
            engineer_count,
            starts,
            starts,
        )
        routing = pywrapcp.RoutingModel(manager)

        def travel_time_callback(from_index: int, to_index: int) -> int:
            """Возвращает время движения между узлами в минутах."""
            # Конечный индекс маршрута нужен OR-Tools для завершения vehicle.
            # В предметной модели это не поездка обратно: последняя заявка
            # является конечной точкой маршрута.
            if routing.IsEnd(to_index):
                return 0
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            from_location = node_location_ids[from_node]
            to_location = node_location_ids[to_node]
            return problem.travel_time_matrix[from_location][to_location]

        transit_callback_index = routing.RegisterTransitCallback(
            travel_time_callback
        )
        def schedule_time_callback(from_index: int, to_index: int) -> int:
            """Возвращает движение плюс работу в исходной заявке, в минутах."""
            from_node = manager.IndexToNode(from_index)
            from_location = node_location_ids[from_node]
            task_at_from = task_by_node.get(from_node)
            service_duration = (
                task_at_from.duration_minutes if task_at_from is not None else 0
            )
            if routing.IsEnd(to_index):
                return service_duration
            to_node = manager.IndexToNode(to_index)
            to_location = node_location_ids[to_node]
            return (
                problem.travel_time_matrix[from_location][to_location]
                + service_duration
            )

        schedule_callback_index = routing.RegisterTransitCallback(
            schedule_time_callback
        )

        def objective_callback(from_index: int, to_index: int) -> int:
            """Возвращает стоимость дуги: расстояние и время движения."""
            if routing.IsEnd(to_index):
                return 0
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            from_location = node_location_ids[from_node]
            to_location = node_location_ids[to_node]
            travel_time = problem.travel_time_matrix[from_location][to_location]
            distance = problem.travel_distance_matrix[from_location][to_location]
            return (
                travel_time * self.config.travel_time_penalty_per_minute
                + int(round(distance * self.config.distance_penalty_per_km))
            )

        objective_callback_index = routing.RegisterTransitCallback(
            objective_callback
        )
        routing.SetArcCostEvaluatorOfAllVehicles(objective_callback_index)
        availability_by_engineer = {
            availability.engineer_id: availability
            for availability in problem.availabilities
        }
        max_available_until = max(
            hhmm_to_minutes(availability.available_until)
            for availability in problem.availabilities
        )
        time_horizon = max(
            max_available_until,
            max(hhmm_to_minutes(task.window_end) for task in eligible_tasks),
        )
        routing.AddDimension(
            schedule_callback_index,
            time_horizon,
            time_horizon,
            False,
            "Time",
        )
        time_dimension = routing.GetDimensionOrDie("Time")

        for vehicle_index, engineer in enumerate(problem.engineers):
            routing.SetFixedCostOfVehicle(
                self.config.used_engineers_penalty,
                vehicle_index,
            )
            availability = availability_by_engineer[engineer.id]
            start_index = routing.Start(vehicle_index)
            end_index = routing.End(vehicle_index)
            time_dimension.CumulVar(start_index).SetRange(
                hhmm_to_minutes(availability.available_from),
                hhmm_to_minutes(availability.available_from),
            )
            # Конечная cumul-переменная означает завершение последней работы.
            # Обратная поездка в стартовую точку в эту модель не входит.
            time_dimension.CumulVar(end_index).SetRange(
                hhmm_to_minutes(availability.available_from),
                hhmm_to_minutes(availability.available_until),
            )

        for task_node, task in task_by_node.items():
            task_index = manager.NodeToIndex(task_node)
            time_dimension.CumulVar(task_index).SetRange(
                hhmm_to_minutes(task.window_start),
                hhmm_to_minutes(task.window_end),
            )
            routing.AddDisjunction(
                [task_index],
                self.config.unassigned_penalty
                * self._priority_multiplier(task),
            )
            for vehicle_index, engineer in enumerate(problem.engineers):
                if not self._engineer_can_execute_task(problem, engineer, task):
                    routing.VehicleVar(task_index).RemoveValue(vehicle_index)

        self._add_resource_constraints(
            problem=problem,
            routing=routing,
            manager=manager,
            time_dimension=time_dimension,
            task_by_node=task_by_node,
        )

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.time_limit.FromTimedelta(
            timedelta(minutes=self.config.time_limit_minutes)
        )

        solution = routing.SolveWithParameters(search_parameters)
        if solution is None:
            raise ValueError("OR-Tools не смог построить решение")

        routes: dict[str, EngineerRoute] = {}
        total_travel_minutes = 0
        total_distance_km = 0.0
        for vehicle_index, engineer in enumerate(problem.engineers):
            index = routing.Start(vehicle_index)
            route_tasks: list[tuple[Task, int]] = []
            route_travel_minutes = 0
            route_distance_km = 0.0

            while not routing.IsEnd(index):
                from_node = manager.IndexToNode(index)
                next_index = solution.Value(routing.NextVar(index))
                to_node = manager.IndexToNode(next_index)
                if not routing.IsEnd(next_index):
                    from_location = node_location_ids[from_node]
                    to_location = node_location_ids[to_node]
                    route_travel_minutes += problem.travel_time_matrix[from_location][
                        to_location
                    ]
                    route_distance_km += self._distance(
                        problem, from_location, to_location
                    )
                task = task_by_node.get(to_node)
                if task is not None:
                    service_start_time = solution.Value(
                        time_dimension.CumulVar(next_index)
                    )
                    route_tasks.append((task, service_start_time))
                index = next_index

            route = self._build_engineer_route(
                engineer_id=engineer.id,
                start_location_id=engineer.start_location_id,
                tasks=route_tasks,
                availability_from=hhmm_to_minutes(
                    availability_by_engineer[engineer.id].available_from
                ),
                problem=problem,
                total_travel_minutes=route_travel_minutes,
                total_distance_km=route_distance_km,
            )
            routes[engineer.id] = route
            total_travel_minutes += route.total_travel_minutes
            total_distance_km += route.total_distance_km

        total_distance_km = math.fsum(
            route.total_distance_km for route in routes.values()
        )

        for task in eligible_tasks:
            task_index = manager.NodeToIndex(task_node_by_id[task.id])
            if solution.Value(routing.ActiveVar(task_index)) == 0:
                unassigned_reasons[task.id] = self._time_unassigned_reason(
                    problem, task
                )

        unassigned_task_ids = tuple(
            task.id for task in problem.tasks if task.id in unassigned_reasons
        )
        return self._build_result(
            problem=problem,
            routes=routes,
            unassigned_reasons=unassigned_reasons,
            total_travel_minutes=total_travel_minutes,
            total_distance_km=total_distance_km,
            unassigned_task_ids=unassigned_task_ids,
        )

    def _build_result(
        self,
        problem: OptimizationProblem,
        routes: dict[str, EngineerRoute],
        unassigned_reasons: dict[str, UnassignedReason],
        total_travel_minutes: int,
        total_distance_km: float,
        unassigned_task_ids: tuple[str, ...] | None = None,
    ) -> OptimizationResult:
        """Собирает результат с разложением objective без SLA."""
        if unassigned_task_ids is None:
            unassigned_task_ids = tuple(
                task.id for task in problem.tasks if task.id in unassigned_reasons
            )
        used_engineers_count = sum(bool(route.stops) for route in routes.values())
        distance_penalty = int(
            round(total_distance_km * self.config.distance_penalty_per_km)
        )
        used_engineers_penalty = (
            used_engineers_count * self.config.used_engineers_penalty
        )
        travel_time_penalty = total_travel_minutes * self.config.travel_time_penalty_per_minute
        unassigned_penalty = sum(
            self.config.unassigned_penalty * self._priority_multiplier(task)
            for task in problem.tasks
            if task.id in unassigned_task_ids
        )
        total_service_minutes = sum(
            route.total_service_minutes for route in routes.values()
        )
        distance_by_engineer = {
            engineer_id: route.total_distance_km
            for engineer_id, route in routes.items()
        }
        travel_time_by_engineer = {
            engineer_id: route.total_travel_minutes
            for engineer_id, route in routes.items()
        }
        assigned_task_count = sum(len(route.stops) for route in routes.values())
        return OptimizationResult(
            routes=routes,
            unassigned_task_ids=unassigned_task_ids,
            unassigned_reasons=unassigned_reasons,
            distance_by_engineer=distance_by_engineer,
            total_distance=total_distance_km,
            travel_time_by_engineer=travel_time_by_engineer,
            total_travel_time=total_travel_minutes,
            used_engineers_count=used_engineers_count,
            assigned_task_count=assigned_task_count,
            unassigned_task_count=len(unassigned_task_ids),
            total_objective=(
                unassigned_penalty
                + used_engineers_penalty
                + distance_penalty
                + travel_time_penalty
            ),
            total_service_minutes=total_service_minutes,
            unassigned_penalty=unassigned_penalty,
            used_engineers_penalty=used_engineers_penalty,
            distance_penalty=distance_penalty,
            travel_time_penalty=travel_time_penalty,
        )

    @staticmethod
    def _empty_routes(problem: OptimizationProblem) -> dict[str, EngineerRoute]:
        """Создаёт пустой маршрут для каждого инженера."""
        return {
            engineer.id: EngineerRoute(
                engineer_id=engineer.id,
                stops=(),
                total_travel_minutes=0,
                total_service_minutes=0,
                total_distance_km=0.0,
            )
            for engineer in problem.engineers
        }

    def _priority_multiplier(self, task: Task) -> int:
        """Возвращает вес неназначения для приоритета заявки."""
        if task.priority.value == "URGENT":
            return self.config.urgent_unassigned_multiplier
        return self.config.normal_unassigned_multiplier

    @staticmethod
    def _distance(
        problem: OptimizationProblem,
        from_location: str,
        to_location: str,
    ) -> float:
        """Возвращает расстояние дуги в километрах."""
        return float(problem.travel_distance_matrix[from_location][to_location])

    @staticmethod
    def _has_eligible_engineer(problem: OptimizationProblem, task: Task) -> bool:
        """Проверяет, есть ли инженер, совместимый с заявкой."""
        return any(
            ORToolsOptimizer._engineer_can_execute_task(problem, engineer, task)
            for engineer in problem.engineers
        )

    @staticmethod
    def _engineer_can_execute_task(
        problem: OptimizationProblem,
        engineer: Engineer,
        task: Task,
    ) -> bool:
        """Проверяет навыки, оборудование и транспорт как жёсткие ограничения."""
        equipment_by_id = {
            resource.id: resource for resource in problem.equipment_resources
        }
        equipment_types = set(engineer.available_equipment)
        equipment_types.update(
            equipment_by_id[resource_id].equipment_type
            for resource_id in engineer.equipment_resource_ids
        )
        vehicle_type = engineer.vehicle_type
        if engineer.vehicle_resource_id is not None:
            vehicle_by_id = {
                resource.id: resource for resource in problem.vehicle_resources
            }
            vehicle_type = vehicle_by_id[engineer.vehicle_resource_id].vehicle_type
        return (
            task.required_skills.issubset(engineer.qualifications)
            and task.required_equipment.issubset(equipment_types)
            and (
                task.required_vehicle_type is None
                or vehicle_type == task.required_vehicle_type
            )
        )

    @staticmethod
    def _engineer_has_required_equipment(
        problem: OptimizationProblem,
        engineer: Engineer,
        task: Task,
    ) -> bool:
        """Проверяет наличие оборудования без проверки транспорта."""
        equipment_by_id = {
            resource.id: resource for resource in problem.equipment_resources
        }
        equipment_types = set(engineer.available_equipment)
        equipment_types.update(
            equipment_by_id[resource_id].equipment_type
            for resource_id in engineer.equipment_resource_ids
        )
        return task.required_equipment.issubset(equipment_types)

    @staticmethod
    def _resource_ids_used_for_task(
        problem: OptimizationProblem,
        engineer: Engineer,
        task: Task,
    ) -> tuple[str, ...]:
        """Возвращает экземпляры ресурсов, занятые во время обслуживания."""
        equipment_by_id = {
            resource.id: resource for resource in problem.equipment_resources
        }
        resource_ids: set[str] = set()
        for equipment_type in task.required_equipment:
            if equipment_type in engineer.available_equipment:
                continue
            matching_resources = sorted(
                resource_id
                for resource_id in engineer.equipment_resource_ids
                if equipment_by_id[resource_id].equipment_type == equipment_type
            )
            if matching_resources:
                resource_ids.add(matching_resources[0])
        if engineer.vehicle_resource_id is not None:
            resource_ids.add(engineer.vehicle_resource_id)
        return tuple(sorted(resource_ids))

    def _add_resource_constraints(
        self,
        problem: OptimizationProblem,
        routing: pywrapcp.RoutingModel,
        manager: pywrapcp.RoutingIndexManager,
        time_dimension: pywrapcp.RoutingDimension,
        task_by_node: dict[int, Task],
    ) -> None:
        """Запрещает пересечение сервисных интервалов одного ресурса."""
        solver = routing.solver()
        usages_by_resource: dict[str, list[tuple[Any, int, Any]]] = {}

        for task_node, task in task_by_node.items():
            if task.duration_minutes == 0:
                continue
            task_index = manager.NodeToIndex(task_node)
            for vehicle_index, engineer in enumerate(problem.engineers):
                resource_ids = self._resource_ids_used_for_task(
                    problem, engineer, task
                )
                if not resource_ids:
                    continue
                assigned_to_engineer = solver.IsEqualCstVar(
                    routing.VehicleVar(task_index), vehicle_index
                )
                use_resource = solver.BoolVar(
                    f"use_resource_{task.id}_{vehicle_index}"
                )
                solver.Add(use_resource <= routing.ActiveVar(task_index))
                solver.Add(use_resource <= assigned_to_engineer)
                solver.Add(
                    use_resource
                    >= routing.ActiveVar(task_index) + assigned_to_engineer - 1
                )
                for resource_id in resource_ids:
                    usages_by_resource.setdefault(resource_id, []).append(
                        (
                            time_dimension.CumulVar(task_index),
                            task.duration_minutes,
                            use_resource,
                        )
                    )

        max_available_until = max(
            hhmm_to_minutes(availability.available_until)
            for availability in problem.availabilities
        )
        max_window_end = max(
            hhmm_to_minutes(task.window_end)
            for task in task_by_node.values()
        )
        max_duration = max(task.duration_minutes for task in task_by_node.values())
        big_m = max(max_available_until, max_window_end) + max_duration + 1
        for resource_id, usages in usages_by_resource.items():
            for left_index, left in enumerate(usages):
                left_start, left_duration, left_use = left
                for right_index in range(left_index + 1, len(usages)):
                    right_start, right_duration, right_use = usages[right_index]
                    both_use = solver.BoolVar(
                        f"both_use_{resource_id}_{left_index}_{right_index}"
                    )
                    solver.Add(both_use <= left_use)
                    solver.Add(both_use <= right_use)
                    solver.Add(both_use >= left_use + right_use - 1)
                    left_before_right = solver.BoolVar(
                        f"resource_order_{resource_id}_{left_index}_{right_index}"
                    )
                    solver.Add(
                        left_start + left_duration
                        <= right_start
                        + big_m * (1 - left_before_right)
                        + big_m * (1 - both_use)
                    )
                    solver.Add(
                        right_start + right_duration
                        <= left_start
                        + big_m * left_before_right
                        + big_m * (1 - both_use)
                    )

    @staticmethod
    def _eligibility_unassigned_reason(
        problem: OptimizationProblem,
        task: Task,
    ) -> UnassignedReason:
        """Возвращает причину, если заявка не может попасть в решатель."""
        has_qualified_engineer = any(
            task.required_skills.issubset(engineer.qualifications)
            for engineer in problem.engineers
        )
        if not has_qualified_engineer:
            return UnassignedReason(
                code=UnassignedReasonCode.MISSING_QUALIFICATION,
                message="Нет инженера с требуемым навыком.",
            )
        has_required_equipment = any(
            task.required_skills.issubset(engineer.qualifications)
            and ORToolsOptimizer._engineer_has_required_equipment(
                problem, engineer, task
            )
            for engineer in problem.engineers
        )
        if not has_required_equipment:
            return UnassignedReason(
                code=UnassignedReasonCode.MISSING_EQUIPMENT,
                message="У подходящих инженеров нет требуемого оборудования.",
            )
        return UnassignedReason(
            code=UnassignedReasonCode.MISSING_VEHICLE_TYPE,
            message="У подходящих инженеров нет требуемого типа транспорта.",
        )

    @staticmethod
    def _time_unassigned_reason(
        problem: OptimizationProblem,
        task: Task,
    ) -> UnassignedReason:
        """Разделяет невозможность окна и выход за рабочую смену."""
        availability_by_engineer = {
            availability.engineer_id: availability
            for availability in problem.availabilities
        }
        can_start_in_window = False
        can_complete_single_task = False
        for engineer in problem.engineers:
            if not ORToolsOptimizer._engineer_can_execute_task(
                problem, engineer, task
            ):
                continue
            availability = availability_by_engineer[engineer.id]
            arrival_time = hhmm_to_minutes(availability.available_from) + problem.travel_time_matrix[
                engineer.start_location_id
            ][task.location_id]
            service_start = max(arrival_time, hhmm_to_minutes(task.window_start))
            if service_start > hhmm_to_minutes(task.window_end):
                continue
            can_start_in_window = True
            finish_time = service_start + task.duration_minutes
            if finish_time <= hhmm_to_minutes(availability.available_until):
                can_complete_single_task = True

        if not can_start_in_window:
            return UnassignedReason(
                code=UnassignedReasonCode.IMPOSSIBLE_TIME_WINDOW,
                message="Ни один инженер не может начать заявку в её окне.",
            )
        if not can_complete_single_task:
            return UnassignedReason(
                code=UnassignedReasonCode.OUTSIDE_WORKING_HOURS,
                message="Работа не помещается в смену.",
            )
        return UnassignedReason(
            code=UnassignedReasonCode.OUTSIDE_WORKING_HOURS,
            message="Заявка не поместилась в смену вместе с другими работами.",
        )

    @staticmethod
    def _build_engineer_route(
        engineer_id: str,
        start_location_id: str,
        tasks: list[tuple[Task, int]],
        availability_from: int,
        problem: OptimizationProblem,
        total_travel_minutes: int,
        total_distance_km: float,
    ) -> EngineerRoute:
        """Строит остановки с временем ``HH:MM`` по найденному порядку."""
        current_time = availability_from
        previous_location_id = start_location_id
        total_service_minutes = 0
        stops: list[RouteStop] = []

        for task, service_start_time in tasks:
            travel_time = problem.travel_time_matrix[previous_location_id][
                task.location_id
            ]
            arrival_time = current_time + travel_time
            service_end_time = service_start_time + task.duration_minutes
            distance = ORToolsOptimizer._distance(
                problem, previous_location_id, task.location_id
            )
            stops.append(
                RouteStop(
                    task_id=task.id,
                    arrival_time=minutes_to_hhmm(arrival_time),
                    service_start_time=minutes_to_hhmm(service_start_time),
                    service_end_time=minutes_to_hhmm(service_end_time),
                    travel_time_from_previous=travel_time,
                    distance_from_previous_km=distance,
                )
            )
            current_time = service_end_time
            previous_location_id = task.location_id
            total_service_minutes += task.duration_minutes

        return EngineerRoute(
            engineer_id=engineer_id,
            stops=tuple(stops),
            total_travel_minutes=total_travel_minutes,
            total_service_minutes=total_service_minutes,
            total_distance_km=total_distance_km,
        )
