"""Реализация маршрутизации на базе Google OR-Tools."""

from __future__ import annotations

from datetime import timedelta
import math
from typing import Any, Mapping, Sequence

# pywrapcp — Python-обёртка над C++ API constraint_solver из OR-Tools.
# routing_enums_pb2 содержит перечисления стратегий поиска, например PATH_CHEAPEST_ARC.
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
    TaskStatus,
    UnassignedReason,
    UnassignedReasonCode,
    VehicleType,
    hhmm_to_minutes,
    minutes_to_hhmm,
)


class ORToolsOptimizer(RouteOptimizer):
    """Решатель VRP с жёсткими ограничениями доменной модели."""

    def __init__(self, config: OptimizerConfig | None = None) -> None:
        """Создаёт решатель с переданной или стандартной конфигурацией."""
        # Конфигурация хранит лимит поиска и все веса objective в одном месте.
        self.config = config or OptimizerConfig()

    def optimize(
        self,
        problem: OptimizationProblem,
        *,
        forced_task_engineer_by_id: Mapping[str, str] | None = None,
        initial_routes_by_engineer: Mapping[str, Sequence[str]] | None = None,
        reference_routes_by_engineer: Mapping[str, Sequence[str]] | None = None,
        time_limit_seconds: int | None = None,
    ) -> OptimizationResult:
        """Определяет назначения, порядок заявок и расписание маршрутов."""
        # Оперативные статусы задачи задают обязательные назначения. Явная
        # фиксация вызывающего кода (например, counterfactual-проверка) может их
        # дополнить, но не должна противоречить уже начатой работе.
        fixed_assignments = dict(problem.fixed_task_engineer_by_id)
        reference_routes = reference_routes_by_engineer or {}
        reference_engineer_by_task = {
            task_id: engineer_id
            for engineer_id, task_ids in reference_routes.items()
            for task_id in task_ids
        }
        reference_predecessor_by_task: dict[str, str] = {}
        for engineer_id, task_ids in reference_routes.items():
            predecessor = f"__START__:{engineer_id}"
            for task_id in task_ids:
                reference_predecessor_by_task[task_id] = predecessor
                predecessor = task_id
        started_assignments = {
            task.id: engineer_id
            for task in problem.planning_tasks
            for engineer_id in [fixed_assignments.get(task.id)]
            if task.status in {TaskStatus.EN_ROUTE, TaskStatus.IN_PROGRESS}
            and engineer_id is not None
        }
        forced_assignments = dict(fixed_assignments)
        for task_id, engineer_id in (forced_task_engineer_by_id or {}).items():
            previous_engineer_id = forced_assignments.get(task_id)
            if previous_engineer_id is not None and previous_engineer_id != engineer_id:
                raise ValueError(
                    f"Заявка {task_id} уже зафиксирована за инженером "
                    f"{previous_engineer_id!r}"
                )
            forced_assignments[task_id] = engineer_id
        eligible_tasks: list[Task] = []
        unassigned_reasons: dict[str, UnassignedReason] = {}
        for task in problem.planning_tasks:
            # На этом этапе отбрасываем только заявки без единого инженера,
            # подходящего по skill/equipment/vehicle. Временные ограничения не
            # проверяем здесь: их должен совместно рассмотреть OR-Tools вместе
            # с выбором инженера и порядка заявок.
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

        # В OR-Tools каждый маршрут называется vehicle. Здесь vehicle — это
        # именно маршрут инженера, а не отдельная модель автомобиля. Поэтому
        # число vehicle равно числу инженеров, участвующих в планировании.
        engineer_count = len(problem.engineers)

        # Переводим наши ID локаций в последовательность логических узлов
        # OR-Tools. Это не список маршрута, а общий каталог узлов модели.
        # Сначала идут стартовые точки инженеров, затем точки заявок:
        #   node 0..engineer_count-1 -> старт соответствующего инженера;
        #   остальные node -> одна заявка из eligible_tasks.
        # Например, при 3 инженерах и 5 заявках список содержит 8 элементов:
        # первые 3 — базы, последние 5 — заявки. Индекс узла сохраняется
        # отдельно от location_id: одинаковые ID локаций всё равно могут быть
        # разными узлами (две заявки в одном месте), а OR-Tools затем создаёт
        # ещё один слой собственных внутренних индексов.
        node_location_ids = [
            problem.route_start_location(engineer) for engineer in problem.engineers
        ] + [task.location_id for task in eligible_tasks]

        # Связываем логический номер узла с объектом Task. Стартовые узлы в
        # этом словаре отсутствуют, поэтому callback понимает, где находится
        # заявка, а где начинается маршрут инженера.
        task_by_node = {
            engineer_count + task_index: task
            for task_index, task in enumerate(eligible_tasks)
        }
        # Обратное отображение нужно после решения: по ID заявки быстро найти
        # индекс узла и прочитать ActiveVar(task_index).
        task_node_by_id = {
            task.id: task_node for task_node, task in task_by_node.items()
        }

        # Для каждого маршрута номер стартового логического узла совпадает с
        # порядком инженера в problem.engineers: vehicle 0 начинается в starts[0]
        # и принадлежит инженеру problem.engineers[0], и так далее.
        starts = list(range(engineer_count))
        manager = pywrapcp.RoutingIndexManager(
            len(node_location_ids),  # number_of_nodes: сколько узлов в общем каталоге.
            engineer_count,  # number_of_vehicles: сколько маршрутов строится одновременно.
            starts,  # starts: логический старт каждого маршрута по индексу vehicle.
            starts,  # ends: логический конец каждого маршрута; здесь тот же индекс технически.
        )
        # RoutingIndexManager — встроенный класс OR-Tools. Он переводит наши
        # логические номера узлов в внутренние индексы RoutingModel. Параметр
        # starts передан дважды потому, что API отдельно требует массивы
        # стартов и концов. Возврат на базу не моделируется: переход в
        # технический End получает нулевую стоимость и не попадает в метрики.
        # RoutingModel создаёт саму VRP-модель поверх менеджера индексов:
        # переменные NextVar, VehicleVar, ActiveVar и целевую функцию.
        routing = pywrapcp.RoutingModel(manager)

        def make_schedule_callback(vehicle_index: int):
            """Создаёт callback расписания для конкретного профиля транспорта."""
            engineer = problem.engineers[vehicle_index]

            def schedule_time_callback(from_index: int, to_index: int) -> int:
                """Возвращает движение плюс обслуживание в минутах."""
                # OR-Tools передаёт внутренние индексы маршрута, а не наши
                # строковые location_id. Сначала преобразуем индекс узла.
                from_node = manager.IndexToNode(from_index)
                from_location = node_location_ids[from_node]
                task_at_from = task_by_node.get(from_node)
                service_duration = (
                    problem.service_duration(task_at_from) if task_at_from is not None else 0
                )
                if routing.IsEnd(to_index):
                    return service_duration
                to_node = manager.IndexToNode(to_index)
                to_location = node_location_ids[to_node]
                return problem.travel_time_between(
                    from_location,
                    to_location,
                    engineer.vehicle_type,
                ) + service_duration

            return schedule_time_callback

        schedule_callback_indices = [
            routing.RegisterTransitCallback(make_schedule_callback(vehicle_index))
            for vehicle_index in range(engineer_count)
        ]
        # Для каждого vehicle регистрируется отдельная функция, потому что
        # OSRM может дать разное время для driving, walking и cycling.

        def make_objective_callback(vehicle_index: int):
            """Создаёт callback стоимости дуги для транспорта инженера."""
            engineer = problem.engineers[vehicle_index]

            def objective_callback(from_index: int, to_index: int) -> int:
                """Возвращает взвешенную стоимость движения по дуге."""
                # Целевая функция OR-Tools должна быть целочисленной. Расстояние
                # переводим из километров в целую стоимость, время уже в минутах.
                if routing.IsEnd(to_index):
                    return 0
                from_node = manager.IndexToNode(from_index)
                to_node = manager.IndexToNode(to_index)
                from_location = node_location_ids[from_node]
                to_location = node_location_ids[to_node]
                travel_time = problem.travel_time_between(
                    from_location,
                    to_location,
                    engineer.vehicle_type,
                )
                distance = problem.travel_distance_between(
                    from_location,
                    to_location,
                    engineer.vehicle_type,
                )
                cost = (
                    travel_time * self.config.travel_time_penalty_per_minute
                    + int(round(distance * self.config.distance_penalty_per_km))
                )
                task_at_to = task_by_node.get(to_node)
                if task_at_to is not None:
                    previous_engineer = reference_engineer_by_task.get(task_at_to.id)
                    if previous_engineer is not None and previous_engineer != engineer.id:
                        cost += self.config.reassignment_penalty
                    expected_predecessor = reference_predecessor_by_task.get(task_at_to.id)
                    if expected_predecessor is not None:
                        task_at_from = task_by_node.get(from_node)
                        actual_predecessor = (
                            task_at_from.id
                            if task_at_from is not None
                            else f"__START__:{engineer.id}"
                        )
                        if actual_predecessor != expected_predecessor:
                            cost += self.config.route_order_change_penalty
                return cost

            return objective_callback

        objective_callback_indices = [
            routing.RegisterTransitCallback(make_objective_callback(vehicle_index))
            for vehicle_index in range(engineer_count)
        ]
        # Основная стоимость дуги включает только движение. Длительность
        # обслуживания нужна для расписания, но не является travel time.
        for vehicle_index, callback_index in enumerate(objective_callback_indices):
            routing.SetArcCostEvaluatorOfVehicle(
                callback_index,  # evaluator_index: функция стоимости дуги.
                vehicle_index,  # vehicle: маршрут конкретного инженера.
            )
        availability_by_engineer = {
            availability.engineer_id: availability
            for availability in problem.availabilities
        }
        # Словарь позволяет получить смену по ID инженера, не меняя порядок
        # инженеров в problem.engineers — этот порядок связан с vehicle index.
        # Временное измерение работает с абсолютными минутами от полуночи.
        # Горизонт должен включать конец самой поздней смены и конец самого
        # позднего окна; slack внутри измерения представляет ожидание.
        max_available_until = max(
            hhmm_to_minutes(availability.available_until)
            for availability in problem.availabilities
        )
        time_horizon = max(
            max_available_until,
            max(hhmm_to_minutes(task.window_end) for task in eligible_tasks),
        )
        time_dimension_name = "Time"  # Имя временного измерения в модели.
        routing.AddDimensionWithVehicleTransits(
            schedule_callback_indices,  # evaluator_indices: callback времени каждого инженера.
            time_horizon,  # slack_max: максимум ожидания перед следующим узлом.
            time_horizon,  # capacity: верхняя граница накопленного времени.
            False,  # fix_start_cumul_to_zero: начало смены не обязано быть 00:00.
            time_dimension_name,  # dimension_name: имя измерения для GetDimensionOrDie.
        )
        # Получаем созданное измерение, чтобы задавать окна и смены через его
        # накопленные временные переменные CumulVar.
        time_dimension = routing.GetDimensionOrDie(time_dimension_name)

        for vehicle_index, engineer in enumerate(problem.engineers):
            routing.SetFixedCostOfVehicle(
                self.config.used_engineers_penalty,  # fixed_cost: цена использования маршрута.
                vehicle_index,  # vehicle: номер инженера/маршрута.
            )
            availability = availability_by_engineer[engineer.id]
            shift_start = problem.route_start_minutes(availability)
            shift_end = hhmm_to_minutes(availability.available_until)
            # Start/End возвращают специальные внутренние индексы маршрута,
            # а CumulVar — переменную накопленного времени в этом индексе.
            start_index = routing.Start(vehicle_index)
            end_index = routing.End(vehicle_index)
            time_dimension.CumulVar(start_index).SetRange(
                shift_start,  # minimum: инженер начинает не раньше начала смены.
                shift_start,  # maximum: инженер начинает ровно в начале смены.
            )
            # Конечная cumul-переменная означает завершение последней работы.
            # Обратная поездка в стартовую точку в эту модель не входит.
            time_dimension.CumulVar(end_index).SetRange(
                shift_start,  # minimum: конец не может быть раньше начала смены.
                shift_end,  # maximum: последняя работа должна закончиться в смену.
            )

        for task_node, task in task_by_node.items():
            # NodeToIndex переводит логический node в индекс, который принимает
            # RoutingModel. Это значение используется во всех ограничениях узла.
            task_index = manager.NodeToIndex(task_node)
            window_start = hhmm_to_minutes(task.window_start)
            window_end = hhmm_to_minutes(task.window_end)
            # Для уже выполняемой заявки исходное окно описывает момент её
            # фактического начала в прошлом. При перепланировании CumulVar
            # представляет начало оставшегося участка «сейчас», поэтому
            # фиксируем его на времени оперативного снимка.
            if (
                problem.planning_time is not None
                and task.status == TaskStatus.IN_PROGRESS
                and task.id in started_assignments
            ):
                fixed_start = problem.route_start_minutes(
                    availability_by_engineer[started_assignments[task.id]]
                )
                window_start = fixed_start
                window_end = fixed_start
            time_dimension.CumulVar(task_index).SetRange(
                window_start,  # minimum: самое раннее начало обслуживания.
                window_end,  # maximum: самое позднее начало обслуживания.
            )
            routing.AddDisjunction(
                [task_index],  # indices: узел заявки, который можно пропустить.
                self.config.unassigned_penalty
                * self._priority_multiplier(task),  # penalty: цена пропуска заявки.
            )
            # AddDisjunction разрешает OR-Tools оставить заявку вне маршрута.
            # Если заявка пропущена, solver платит penalty; hard constraints
            # при этом по-прежнему запрещают недопустимые назначения.
            for vehicle_index, engineer in enumerate(problem.engineers):
                if not self._engineer_can_execute_task(problem, engineer, task):
                    # VehicleVar хранит номер маршрута, которому может
                    # принадлежать узел. RemoveValue оставляет заявку в модели,
                    # но запрещает конкретного несовместимого инженера.
                    routing.VehicleVar(task_index).RemoveValue(vehicle_index)
            forced_engineer_id = forced_assignments.get(task.id)
            if forced_engineer_id is not None:
                forced_vehicle_index = next(
                    (
                        index
                        for index, engineer in enumerate(problem.engineers)
                        if engineer.id == forced_engineer_id
                    ),
                    None,
                )
                if forced_vehicle_index is None:
                    raise ValueError(
                        f"Не найден инженер {forced_engineer_id!r} для принудительного назначения"
                    )
                # VehicleVar хранит номер маршрута заявки. SetValue оставляет
                # в модели только выбранного инженера для counterfactual-расчёта.
                routing.VehicleVar(task_index).SetValue(forced_vehicle_index)
                # Для выполняемой/текущей заявки недостаточно указать vehicle:
                # disjunction иначе всё ещё могла бы сделать узел неактивным.
                routing.ActiveVar(task_index).SetValue(1)

        # Уже выполняемая заявка или заявка, к которой инженер едет, является
        # первой изменяемой точкой его текущего маршрута. Фиксация Start->task
        # запрещает solver вставить перед ней ещё одну новую работу.
        engineer_index_by_id = {
            engineer.id: index for index, engineer in enumerate(problem.engineers)
        }
        for task in eligible_tasks:
            # В режиме полного перераспределения статус заявки не имеет силы,
            # поэтому ориентируемся на фактическую карту принудительных
            # назначений, а не напрямую на Task.status.
            if task.id not in started_assignments:
                continue
            engineer_id = started_assignments[task.id]
            task_index = manager.NodeToIndex(task_node_by_id[task.id])
            routing.NextVar(
                routing.Start(engineer_index_by_id[engineer_id])
            ).SetValue(task_index)

        self._add_resource_constraints(
            # Добавляет дополнительные hard constraints для отдельных
            # экземпляров оборудования и транспорта, если они заданы.
            problem=problem,
            routing=routing,
            manager=manager,
            time_dimension=time_dimension,
            task_by_node=task_by_node,
        )

        # Создаём объект RoutingSearchParameters — набор настроек алгоритма
        # поиска OR-Tools. Здесь меняем только стратегию первого решения и
        # ограничение времени, остальные параметры оставляем стандартными.
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            # PATH_CHEAPEST_ARC строит первое решение, выбирая очередную
            # доступную дугу с минимальной стоимостью objective callback.
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        # time_limit задаётся объектом Duration. В domain всё время в минутах;
        # timedelta только переводит настроенный лимит в тип, который ожидает
        # API OR-Tools.
        search_parameters.time_limit.FromTimedelta(
            timedelta(
                seconds=(
                    time_limit_seconds
                    if time_limit_seconds is not None
                    else self.config.time_limit_minutes * 60
                )
            )
        )

        # SolveWithParameters запускает поиск и возвращает Assignment — набор
        # найденных значений NextVar, ActiveVar, VehicleVar и CumulVar.
        solution = None
        if initial_routes_by_engineer is None and forced_assignments:
            # PATH_CHEAPEST_ARC плохо находит первое решение, когда несколько
            # узлов уже обязаны принадлежать конкретным маршрутам. Передаём
            # минимальный допустимый warm start только из зафиксированных
            # заявок; остальные заявки solver сам вставит или оставит inactive.
            fixed_tasks_by_engineer: dict[str, list[Task]] = {
                engineer.id: [] for engineer in problem.engineers
            }
            for task in eligible_tasks:
                engineer_id = forced_assignments.get(task.id)
                if engineer_id is not None:
                    fixed_tasks_by_engineer[engineer_id].append(task)
            initial_routes_by_engineer = {
                engineer_id: tuple(
                    task.id
                    for task in sorted(
                        tasks,
                        key=lambda item: (
                            hhmm_to_minutes(item.window_start),
                            hhmm_to_minutes(item.window_end),
                            item.id,
                        ),
                    )
                )
                for engineer_id, tasks in fixed_tasks_by_engineer.items()
            }
        if initial_routes_by_engineer:
            task_by_id = {task.id: task for task in eligible_tasks}
            initial_routes = [
                [
                    task_node_by_id[task_id]
                    for task_id in initial_routes_by_engineer.get(engineer.id, ())
                    if task_id in task_node_by_id
                    and self._engineer_can_execute_task(
                        problem, engineer, task_by_id[task_id]
                    )
                    and forced_assignments.get(task_id, engineer.id) == engineer.id
                ]
                for engineer in problem.engineers
            ]
            # ReadAssignmentFromRoutes превращает уже построенные маршруты в
            # Assignment. Если исходный план не подходит новой фиксации, OR-
            # Tools вернёт None, и ниже будет обычный поиск с нуля.
            initial_assignment = routing.ReadAssignmentFromRoutes(
                initial_routes,
                True,  # ignore_inactive_indices: пропускать заявки вне списка маршрутов.
            )
            if initial_assignment is not None:
                solution = routing.SolveFromAssignmentWithParameters(
                    initial_assignment,
                    search_parameters,
                )
        if solution is None:
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

            # Идём по цепочке NextVar от технического Start до End. Дуга в End
            # нужна OR-Tools для завершения маршрута, но в нашем домене она
            # имеет нулевые travel time и distance и не добавляется в метрики.
            while not routing.IsEnd(index):
                from_node = manager.IndexToNode(index)
                # NextVar(index) — переменная OR-Tools со следующим узлом
                # маршрута. Assignment хранит выбранное значение этой
                # переменной, которое читается через solution.Value(...).
                next_index = solution.Value(routing.NextVar(index))
                to_node = manager.IndexToNode(next_index)
                if not routing.IsEnd(next_index):
                    from_location = node_location_ids[from_node]
                    to_location = node_location_ids[to_node]
                    route_travel_minutes += problem.travel_time_between(
                        from_location,
                        to_location,
                        engineer.vehicle_type,
                    )
                    route_distance_km += self._distance(
                        problem,
                        from_location,
                        to_location,
                        engineer.vehicle_type,
                    )
                task = task_by_node.get(to_node)
                if task is not None:
                    # CumulVar заявки — это начало обслуживания: callback уже
                    # добавил дорогу и, если нужно, OR-Tools добавил ожидание.
                    service_start_time = solution.Value(
                        time_dimension.CumulVar(next_index)
                    )
                    route_tasks.append((task, service_start_time))
                index = next_index

            route = self._build_engineer_route(
                engineer_id=engineer.id,
                start_location_id=problem.route_start_location(engineer),
                vehicle_type=engineer.vehicle_type,
                tasks=route_tasks,
                availability_from=problem.route_start_minutes(
                    availability_by_engineer[engineer.id]
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
            task.id for task in problem.planning_tasks if task.id in unassigned_reasons
        )
        return self._build_result(
            problem=problem,
            routes=routes,
            unassigned_reasons=unassigned_reasons,
            total_travel_minutes=total_travel_minutes,
            total_distance_km=total_distance_km,
            unassigned_task_ids=unassigned_task_ids,
            reference_routes_by_engineer=reference_routes,
        )

    def _build_result(
        self,
        problem: OptimizationProblem,
        routes: dict[str, EngineerRoute],
        unassigned_reasons: dict[str, UnassignedReason],
        total_travel_minutes: int,
        total_distance_km: float,
        unassigned_task_ids: tuple[str, ...] | None = None,
        reference_routes_by_engineer: Mapping[str, Sequence[str]] | None = None,
    ) -> OptimizationResult:
        """Собирает метрики и четыре компонента целевой функции."""
        if unassigned_task_ids is None:
            unassigned_task_ids = tuple(
                task.id for task in problem.planning_tasks if task.id in unassigned_reasons
            )
        used_engineers_count = sum(bool(route.stops) for route in routes.values())
        # Сначала задача штрафуется за неназначение, затем за число маршрутов,
        # расстояние и travel time. Эти четыре суммы должны совпасть с
        # total_objective; hard constraints сюда не попадают.
        distance_penalty = int(
            round(total_distance_km * self.config.distance_penalty_per_km)
        )
        used_engineers_penalty = (
            used_engineers_count * self.config.used_engineers_penalty
        )
        travel_time_penalty = total_travel_minutes * self.config.travel_time_penalty_per_minute
        unassigned_penalty = sum(
            self.config.unassigned_penalty * self._priority_multiplier(task)
            for task in problem.planning_tasks
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
        reassigned_task_count, reordered_task_count = self._plan_disruption_metrics(
            routes, reference_routes_by_engineer or {}
        )
        plan_disruption_penalty = (
            reassigned_task_count * self.config.reassignment_penalty
            + reordered_task_count * self.config.route_order_change_penalty
        )
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
                + plan_disruption_penalty
            ),
            total_service_minutes=total_service_minutes,
            unassigned_penalty=unassigned_penalty,
            used_engineers_penalty=used_engineers_penalty,
            distance_penalty=distance_penalty,
            travel_time_penalty=travel_time_penalty,
            plan_disruption_penalty=plan_disruption_penalty,
            reassigned_task_count=reassigned_task_count,
            reordered_task_count=reordered_task_count,
        )

    @staticmethod
    def _plan_disruption_metrics(
        routes: Mapping[str, EngineerRoute],
        reference_routes: Mapping[str, Sequence[str]],
    ) -> tuple[int, int]:
        """Считает переносы и изменения предшественника относительно старого плана."""
        old_engineer: dict[str, str] = {}
        old_predecessor: dict[str, str] = {}
        for engineer_id, task_ids in reference_routes.items():
            predecessor = f"__START__:{engineer_id}"
            for task_id in task_ids:
                old_engineer[task_id] = engineer_id
                old_predecessor[task_id] = predecessor
                predecessor = task_id

        reassigned = 0
        reordered = 0
        for engineer_id, route in routes.items():
            predecessor = f"__START__:{engineer_id}"
            for stop in route.stops:
                task_id = stop.task_id
                if task_id in old_engineer and old_engineer[task_id] != engineer_id:
                    reassigned += 1
                if task_id in old_predecessor and old_predecessor[task_id] != predecessor:
                    reordered += 1
                predecessor = task_id
        return reassigned, reordered

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
        vehicle_type: VehicleType,
    ) -> float:
        """Возвращает расстояние дуги в километрах."""
        return problem.travel_distance_between(
            from_location,
            to_location,
            vehicle_type,
        )

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
        """Проверяет навыки, оборудование и транспорт как жёсткие ограничения.

        ``available_equipment`` содержит типы оборудования напрямую. Если
        включена модель отдельных ресурсов, их типы добавляются из
        ``equipment_resource_ids``; это позволяет сохранить простой сценарий
        без бронирования ресурсов.
        """
        if engineer.id in problem.unavailable_engineer_ids:
            return False
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
        # routing.solver() возвращает низкоуровневый CP-SAT/constraint_solver
        # объект, через который создаются дополнительные булевы переменные и
        # логические ограничения поверх RoutingModel.
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
                    routing.VehicleVar(task_index),  # кому назначен узел.
                    vehicle_index,  # константа: номер проверяемого инженера.
                )
                use_resource = solver.BoolVar(
                    f"use_resource_{task.id}_{vehicle_index}"  # имя диагностической переменной.
                )
                # use_resource истинна только тогда, когда заявка активна и
                # назначена именно этому инженеру: три неравенства ниже
                # кодируют логическое AND через линейные ограничения.
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
                        f"both_use_{resource_id}_{left_index}_{right_index}"  # имя AND-переменной.
                    )
                    solver.Add(both_use <= left_use)
                    solver.Add(both_use <= right_use)
                    solver.Add(both_use >= left_use + right_use - 1)
                    left_before_right = solver.BoolVar(
                        f"resource_order_{resource_id}_{left_index}_{right_index}"  # порядок двух интервалов.
                    )
                    # Big-M отключает эти два ограничения, когда хотя бы одна
                    # заявка не использует ресурс. Если используют обе, одна
                    # из заявок обязана полностью закончиться до другой.
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
            arrival_time = hhmm_to_minutes(availability.available_from) + problem.travel_time_between(
                engineer.start_location_id,
                task.location_id,
                engineer.vehicle_type,
            )
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
        vehicle_type: VehicleType,
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
            travel_time = problem.travel_time_between(
                previous_location_id,
                task.location_id,
                vehicle_type,
            )
            arrival_time = current_time + travel_time
            service_duration = problem.service_duration(task)
            service_end_time = service_start_time + service_duration
            distance = ORToolsOptimizer._distance(
                problem,
                previous_location_id,
                task.location_id,
                vehicle_type,
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
            total_service_minutes += service_duration

        return EngineerRoute(
            engineer_id=engineer_id,
            stops=tuple(stops),
            total_travel_minutes=total_travel_minutes,
            total_service_minutes=total_service_minutes,
            total_distance_km=total_distance_km,
        )
