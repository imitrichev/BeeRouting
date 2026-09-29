# Логика оптимизации, метрики и ограничения

В проекте четыре реализации интерфейса `RouteOptimizer`. Надёжным основным
решателем является `ORToolsOptimizer`; остальные нужны как baseline или как
экспериментальные варианты сравнения.

## Общая постановка

Для каждой заявки нужно выбрать инженера и позицию заявки в его маршруте.
После этого определяется расписание:

```text
arrival = предыдущий момент + travel_time
service_start = max(arrival, window_start)
service_end = service_start + duration_minutes
```

`service_start` должен попасть в закрытый интервал `[window_start,
window_end]`, а `service_end` не может быть позже конца смены инженера.
Если инженер приехал раньше окна, он ждёт. Возвращение в офис после последней
заявки не добавляется.

Внешняя routing-матрица задаётся для пар `from_location -> to_location`.
Стартовая точка инженера — первая точка его маршрута. В заявках с одинаковым
адресом всё равно могут быть разные узлы, потому что это разные работы.

Основные hard constraints:

1. все `required_skills` заявки входят в `Engineer.qualifications`;
2. при наличии `required_vehicle_type` он совпадает с типом инженера;
3. при включённом equipment-режиме запас роутеров инженера покрывает сумму
   `required_router_count` его маршрута;
4. отдельные экземпляры ресурсов не используются одновременно несколькими
   инженерами;
5. начало работы попадает во временное окно;
6. вся работа с дорогой завершается до `available_until`;
7. `EN_ROUTE` и `IN_PROGRESS` остаются за текущим инженером;
8. в статусном режиме `COMPLETED` и `CANCELLED` не входят в новый план.

Hard constraint не превращается в штраф. Если допустимый маршрут не найден,
заявка остаётся в `unassigned_task_ids`, а `unassigned_reasons` содержит код
и сообщение. Минимальные коды: `missing_qualification`, `missing_equipment`,
`missing_vehicle_type`, `impossible_time_window`,
`outside_working_hours`.

## Domain-модели

```python
OptimizationProblem(
    engineers=...,
    availabilities=...,
    tasks=...,
    travel_time_matrix=...,
    travel_distance_matrix=...,
    travel_time_matrices_by_vehicle=...,
    travel_distance_matrices_by_vehicle=...,
)
```

Время на границе модели — `HH:MM`, длительность и travel time — целые минуты,
расстояние — километры. Профильные матрицы являются важной частью модели:
`problem.travel_time_between(..., engineer.vehicle_type)` выбирает матрицу
конкретного инженера. Поэтому один общий `RoutingModel` может содержать
несколько vehicle-маршрутов, но callback времени и callback стоимости для
каждого маршрута используют его собственный транспортный профиль.

`OptimizationResult` возвращает:

- `routes` с `RouteStop` по каждому инженеру;
- `unassigned_task_ids` и `unassigned_reasons`;
- `distance_by_engineer`, `total_distance`;
- `travel_time_by_engineer`, `total_travel_time`;
- `used_engineers_count`, `assigned_task_count`, `unassigned_task_count`;
- `unassigned_penalty`, `used_engineers_penalty`, `distance_penalty`,
  `travel_time_penalty`, `plan_disruption_penalty` и `total_objective`.

## ORToolsOptimizer

`pywrapcp` — это Python-обёртка над C++-модулем OR-Tools
`constraint_solver`. Классы ниже являются встроенными классами Google
OR-Tools:

- [`RoutingIndexManager`](https://developers.google.com/optimization/reference/constraint_solver/routing_index_manager/RoutingIndexManager) — переводит логические номера узлов в внутренние индексы solver;
- [`RoutingModel`](https://developers.google.com/optimization/reference/constraint_solver/routing/RoutingModel) — хранит VRP-модель, переменные маршрутов и ограничения;
- [`RoutingDimension`](https://developers.google.com/optimization/reference/constraint_solver/routing/RoutingDimension) — накопленное время или расход ресурса;
- [`RoutingSearchParameters`](https://developers.google.com/optimization/routing/routing_options) — параметры поиска и лимит времени;
- [задачи маршрутизации OR-Tools](https://developers.google.com/optimization/routing/routing_tasks?hl=ru) — официальные примеры API.

### 1. Логические узлы

Сначала строится единый список:

```python
node_location_ids = (
    [engineer.start_location_id for engineer in problem.engineers]
    + [task.location_id for task in eligible_tasks]
)
```

Первые узлы — стартовые точки маршрутов, затем идут точки заявок. Это именно
каталог узлов, а не готовые маршруты. Отдельное отображение связывает номер
узла с `Task`, чтобы callbacks могли понять, где заявка, а где старт.

### 2. Почему `starts` передаётся дважды

```python
starts = list(range(engineer_count))
manager = pywrapcp.RoutingIndexManager(
    len(node_location_ids),  # number_of_nodes: число логических узлов
    engineer_count,          # number_of_vehicles: число маршрутов
    starts,                  # starts: стартовый узел каждого маршрута
    starts,                  # ends: конечный узел каждого маршрута
)
```

Сигнатура требует отдельные массивы `starts` и `ends`. В проекте они совпадают
технически: каждый маршрут начинается в своём стартовом узле и заканчивается
в специальном внутреннем `End` OR-Tools, который связан с тем же исходным
узлом. Это не означает, что инженер возвращается в офис. Переход в `End`
имеет нулевую стоимость и не попадает в результат как обратная поездка.

В OR-Tools слово `vehicle` означает маршрут. В BeeRouting этот маршрут
принадлежит инженеру. Это не отдельное транспортное средство и не означает,
что приложение распределяет один автомобиль между инженерами.

### 3. Callback времени

Для каждого инженера регистрируется свой callback:

```python
return problem.travel_time_between(
    from_location,
    to_location,
    engineer.vehicle_type,
) + service_duration
```

`RegisterTransitCallback` ([документация](https://developers.google.com/optimization/reference/constraint_solver/routing/RoutingModel#RegisterTransitCallback)) регистрирует функцию стоимости перехода. В callback
передаются внутренние индексы, поэтому сначала выполняется
`manager.IndexToNode(index)`. Время перехода включает дорогу от предыдущей
точки и обслуживание заявки в исходной точке. Так накопленная величина
временного измерения на следующем узле означает начало обслуживания.

### 4. Временное измерение

```python
routing.AddDimensionWithVehicleTransits(
    schedule_callback_indices,  # evaluator_indices: callback времени каждого инженера
    time_horizon,                # slack_max: максимум ожидания
    time_horizon,                # capacity: верхняя граница накопленного времени
    False,                       # fix_start_cumul_to_zero: старт не обязан быть 00:00
    "Time",                     # dimension_name: имя измерения
)
time_dimension = routing.GetDimensionOrDie("Time")
```

`AddDimensionWithVehicleTransits` создаёт накопленное измерение, причём для
каждого маршрута может использовать свой callback. Официальное описание:
[`AddDimensionWithVehicleTransits`](https://developers.google.com/optimization/reference/constraint_solver/routing/RoutingModel#AddDimensionWithVehicleTransits).

Далее через `CumulVar` задаются интервалы:

```python
time_dimension.CumulVar(start_index).SetRange(
    shift_start,  # minimum: начало смены
    shift_start,  # maximum: старт ровно в начале расчётного участка
)
time_dimension.CumulVar(task_index).SetRange(
    window_start,  # minimum: самое раннее начало работы
    window_end,    # maximum: самое позднее начало работы
)
time_dimension.CumulVar(end_index).SetRange(
    shift_start,  # minimum: маршрут не заканчивается до его начала
    shift_end,    # maximum: работа должна завершиться в смену
)
```

Свободный slack между прибытием и окном — это ожидание. Окно относится к
началу работы, а не к прибытию.

### 5. Arc cost и число инженеров

`SetArcCostEvaluatorOfVehicle` назначает callback стоимости дуг каждому
маршруту. Стоимость дуги состоит из:

```text
travel_time_minutes * travel_time_penalty_per_minute
+ distance_km * distance_penalty_per_km
```

Округление расстояния до целой стоимости нужно потому, что внутренняя
целочисленная objective OR-Tools не принимает дробный километраж.

`SetFixedCostOfVehicle` ([документация](https://developers.google.com/optimization/reference/constraint_solver/routing/RoutingModel#SetFixedCostOfVehicle)) добавляет `used_engineers_penalty` за
непустой маршрут. Поэтому solver предпочитает объединять заявки у уже
задействованных инженеров, если это не нарушает hard constraints и не создаёт
более дорогого допустимого плана.

### 6. Неназначенная заявка

```python
routing.AddDisjunction(
    [task_index],                    # indices: узел заявки
    unassigned_penalty * multiplier, # penalty: цена пропуска
)
```

[`AddDisjunction`](https://developers.google.com/optimization/reference/constraint_solver/routing/RoutingModel#AddDisjunction) разрешает оставить узел вне маршрутов и
штрафует это решение. Несовместимые vehicle удаляются через
`routing.VehicleVar(task_index).RemoveValue(vehicle_index)`, поэтому штраф не
превращает нарушение навыка, транспорта или окна в допустимое назначение.
Квалификационно, транспортно или оборудовательно невозможные заявки
отбрасываются ещё до построения модели, если для них нет ни одного кандидата.

Множитель неназначения берётся из `OptimizerConfig`:

- авария — `emergency_unassigned_multiplier`;
- подключение — `connection_unassigned_multiplier`;
- локальная работа — `local_unassigned_multiplier`;
- дозаказ — `equipment_order_unassigned_multiplier`.

Дополнительно применяется множитель `URGENT` относительно `NORMAL`. Это
приоритет objective, а не обязательное правило «подключение всегда раньше
ремонта».

### 7. Оборудование и отдельные ресурсы

При `consider_equipment=True` вызываются
`RegisterUnaryTransitCallback` и
[`AddDimensionWithVehicleCapacity`](https://developers.google.com/optimization/reference/constraint_solver/routing/RoutingModel#AddDimensionWithVehicleCapacity).
Callback возвращает расход роутеров в узле заявки, а capacity маршрута равна
утреннему запасу инженера. Slack равен нулю: пополнения по ходу дня нет.

Если в `OptimizationProblem` заданы отдельные экземпляры оборудования или
транспорта, дополнительная проверка временных интервалов запрещает пересечение
использования одним экземпляром. Простая модель `available_router_count` не
создаёт расписание общего склада.

### 8. Фиксация начатых работ

Для `EN_ROUTE` и `IN_PROGRESS` solver получает `VehicleVar.SetValue`, а
`ActiveVar.SetValue(1)`. Для первой начатой заявки дополнительно фиксируется
`NextVar` от стартового узла. Это не позволяет вставить перед уже начатой
работой новую заявку. В обычном status-aware режиме `COMPLETED` и `CANCELLED`
вообще не передаются в новый маршрут.

`ASSIGNED` переносим по умолчанию. Режим `preserve_assigned_tasks=True`
добавляет эти заявки в фиксированные назначения. `ignore_task_statuses=True`
строит новый план по всем заявкам и нужен для полного утреннего
перераспределения или сравнения solver’ов.

### 9. Запуск поиска

```python
search_parameters = pywrapcp.DefaultRoutingSearchParameters()
search_parameters.first_solution_strategy = (
    routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
)
search_parameters.time_limit.FromTimedelta(...)
solution = routing.SolveWithParameters(search_parameters)
```

[`DefaultRoutingSearchParameters`](https://developers.google.com/optimization/reference/constraint_solver/routing_enums_pb2) задаёт настройки поиска,
`PATH_CHEAPEST_ARC` строит первое решение по дешёвым доступным дугам, а
`SolveWithParameters` запускает поиск. Лимит OR-Tools задаётся
`OptimizerConfig.time_limit_minutes`; в API MVP он установлен сервисом в одну
минуту. При отсутствии допустимого решения возвращается ошибка solver, а не
фальшивый маршрут.

При counterfactual-проверке объяснения передаются текущие маршруты как
исходный вариант, фиксируется проверяемое назначение, а для найденного плана
считается число переносов и изменений предшественников. Компонент
`plan_disruption_penalty` входит в ту же objective, что и основной расчёт.

## Остальные solver’ы

### GreedyBaselineOptimizer

Baseline реализует точное правило из ТЗ: заявки обрабатываются в порядке
входных данных, инженеры — в порядке входных данных, назначается первая
допустимая бригада, а порядок визитов равен порядку назначения. Он использует
те же hard constraints, routing data и формат `OptimizationResult`, но не
делает глобального поиска. Поэтому его результат — контрольная нижняя планка,
а не эталон математического оптимума.

### ICOOptimizer

ICO-DE кодирует каждую заявку random keys. Один ключ выбирает инженера или
неназначение, второй задаёт порядок внутри маршрута. Декодер проверяет тот же
набор ограничений и начинает с результата Baseline. Это исследовательский
solver для сравнения и возможной будущей improvement-фазы; основной OR-Tools
им не заменяется.

### TimefoldOptimizer

Timefold создаёт planning list variable: у каждого инженера есть список задач,
а задача может остаться неназначенной. Constraint streams разделяют hard,
medium и soft уровни: совместимость, временные окна, смена, фиксированные
статусы и ресурсы находятся в hard-части; выполнение заявок, число инженеров,
расстояние и travel time — в objective. Solver получает уже построенные
матрицы и не зависит от OSRM напрямую.

Timefold запускается в отдельном Python-окружении с совместимым Python и JDK
17+. В проекте подготовлен JDK 21. Если Java недоступна, benchmark пропускает
Timefold и продолжает Baseline/OR-Tools.

## RoutingProvider

Для `PUBLIC_TRANSPORT` применяется двухэтапный расчёт. Сначала solver получает
полную статическую матрицу OSRM `driving × 2`. Затем только дуги найденных
маршрутов общественного транспорта уточняются через OTP на расчётное время
отправления: начало смены для первой дуги и `service_end_time` предыдущей
заявки для последующих. При изменении матрицы OR-Tools получает первый план как
initial solution и запускается повторно. HTTP-запросы никогда не выполняются
внутри transit callback solver.

Если OTP не нашёл маршрут или недоступен, значение пары не меняется. Благодаря
этому ограниченное Москвой GTFS-покрытие не делает областные заявки
недопустимыми: для них продолжает действовать fallback `car × 2`.

`RoutingProvider` предоставляет:

- матрицу времени в минутах;
- матрицу расстояния в километрах;
- GeoJSON geometry выбранного маршрута.

`InMemoryRoutingProvider` возвращает явно переданные матрицы и используется в
тестах. `CoordinateRoutingProvider` считает haversine-расстояние по широте и
долготе и переводит его во время по демонстрационной скорости. Это расстояние
по прямой, не по дорогам.

`OSRMRoutingProvider` вызывает OSRM Table для матриц и Route для геометрии.
Для OSRM включены:

- кэш отдельных направленных пар в SQLite;
- кэш целых таблиц в NPZ;
- кэш ответов в памяти текущего процесса;
- отдельные base URL/profile для типов транспорта.

Ключи кэша учитывают координаты, порядок локаций, endpoint, профиль и
множитель общественного транспорта. Кэш ускоряет подготовку матриц, но не
ускоряет поиск OR-Tools. `OSRM_PAIR_CACHE_PATH=off` и
`OSRM_MATRIX_CACHE_PATH=off` отключают уровни кэширования.

## Объяснимость

`ExplanationEngine` не просит OR-Tools «объяснить» внутренний ход поиска.
Вместо этого он делает воспроизводимую проверку:

1. детерминированно отбрасывает несовместимых инженеров и пробует вставку в
   текущий маршрут;
2. для оставшихся кандидатов запускает короткий counterfactual OR-Tools с
   текущим планом, обязательным кандидатом и той же objective.

В результат попадают причины по навыку, транспорту, оборудованию, расписанию,
изменение пробега, времени, числа инженеров и плановых переносов. Важные
факты отмечаются `must_mention=true`. LLM получает только этот JSON; текст не
может менять назначение и не должен придумывать отсутствующие факты.

## Проверка корректности

```bash
.venv/bin/python -m pytest backend/optimization/tests -q
.venv/bin/python backend/web_mvp/manage.py test \
  backend.web_mvp.api_v2.tests backend.web_mvp.api_v2.tests_planning -v 1
```

Тесты проверяют hard constraints, несколько заявок у одного инженера,
разные транспортные матрицы, статусы, перепланирование, оборудование,
объяснения и API v2. Для карт и реальных дорог отдельно запускается benchmark,
описанный в [benchmarks.md](benchmarks.md).
