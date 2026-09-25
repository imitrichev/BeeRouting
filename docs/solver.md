# Как работает `ORToolsOptimizer`

Этот документ описывает текущую реализацию математического ядра в
`backend/optimization`. Он рассчитан на человека, который впервые видит
Google OR-Tools и хочет понять, откуда берутся назначения, порядок заявок и
времена остановок.

## Что решает текущая версия

На вход решатель получает `OptimizationProblem`:

- `engineers` — список инженеров, их квалификации, оборудования и стартовые
  локации;
- `availabilities` — начало и конец рабочей смены каждого инженера;
- `tasks` — заявки с локацией, обязательными навыками, оборудованием, типом
  транспорта, длительностью и временным окном;
- `travel_time_matrix` — готовая внешняя матрица времени движения в минутах;
- `travel_distance_matrix` — готовая внешняя матрица расстояний в километрах.
  Обе матрицы могут быть получены через `RoutingProvider`.

На выходе `OptimizationResult` содержит `EngineerRoute` для каждого инженера.
Каждый маршрут имеет упорядоченные `RouteStop`. Также возвращаются
`distance_by_engineer`, `total_distance`, `travel_time_by_engineer`,
`total_travel_time`, `used_engineers_count`, `assigned_task_count`,
`unassigned_task_count` и `total_objective`. Время остановок на границе результата
выводится как `HH:MM`, а длительности и время движения — в минутах.

### Количественный учёт роутеров

Основной сценарий оборудования использует два целых поля:
`Engineer.available_router_count` — запас инженера в начале дня и
`Task.required_router_count` — расход на заявку. При включённом
`OptimizationProblem.consider_equipment` сумма требований всех заявок маршрута
не может превышать запас инженера. Пополнение и передача роутеров между
инженерами в течение дня не моделируются.

В демонстрационных данных утренний запас рассчитан по контрольным назначениям.
Для двух заявок района «Восток», которые в контрольном CSV ещё не имели
исполнителя, резерв добавлен подходящей по квалификации бригаде с минимальным
исходным запасом. Поэтому суммарный запас каждого района равен суммарной
потребности его синтетических заявок.

При выключенной опции количество роутеров не ограничивает решение. Во
frontend режим задаёт флажок «Учитывать оборудование», а в benchmark —
аргумент `--consider-equipment`.

В OR-Tools это hard constraint: `RoutingModel.AddDimensionWithVehicleCapacity`
создаёт измерение `Routers`; callback возвращает расход в узле заявки, а
ёмкость каждого vehicle равна запасу соответствующего инженера.

Сейчас реализованы следующие правила:

1. заявка может быть назначена инженеру только при выполнении всех жёстких
   ограничений: квалификации инженера покрывают `required_skills`, при
   включённом учёте оборудования доступный запас покрывает требования, а при наличии
   `required_vehicle_type` тип транспорта совпадает;
2. заявка должна быть обслужена внутри своего временного окна;
3. маршрут должен закончить последнюю работу до `available_until`.

Инженер может приехать раньше окна и ждать. Время ожидания и длительность
обслуживания влияют на допустимость маршрута, но не входят в компонент
Компоненты `total_objective` включают штраф за неназначение, число инженеров,
расстояние и travel time. Если заявка не может быть назначена, к стоимости
добавляется настроенный `unassigned_penalty` с учётом типа работ.
Возвращение на стартовую локацию после последней заявки в модель не входит.

Неназначенные заявки возвращаются в `unassigned_task_ids`, а в
`unassigned_reasons` для каждой заявки хранится `UnassignedReason` с кодом и
понятным сообщением. Поддерживаются коды `missing_qualification`,
`missing_equipment`, `missing_vehicle_type`, `impossible_time_window` и
`outside_working_hours`.

Динамическое распределение транспорта и отдельное расписание автомобилей
пока не моделируются. Закреплённые экземпляры оборудования и транспорта
учитываются при проверке доступности и конфликтов, а
`required_vehicle_type`, если он задан, проверяется как жёсткое ограничение.
Для web MVP доступен `OSRMRoutingProvider`: он получает матрицы через OSRM и
возвращает GeoJSON geometry маршрута. Сам `ORToolsOptimizer` по-прежнему не
зависит от OSRM и работает с уже подготовленными routing data.

## Предметные модели

### `Engineer`

```python
Engineer(
    id="e1",
    name="Анна",
    qualifications=frozenset({Skill.LOCAL_WORKS, Skill.CONNECTION_AND_UPSELL}),
    start_location_id="base-1",
    available_equipment=frozenset({"multimeter"}),
    vehicle_type=VehicleType.CAR,
)
```

Инженер не хранит назначенные заявки. Его маршрут появляется только в
`OptimizationResult`.

При необходимости `OptimizationProblem` также содержит отдельные
`EquipmentResource` и `VehicleResource`. Их количество задаётся количеством
экземпляров в соответствующем списке, а инженер ссылается на закреплённые
экземпляры через `equipment_resource_ids` и `vehicle_resource_id`. Один и тот
же экземпляр может быть указан у нескольких инженеров, но его сервисные
интервалы не могут пересекаться. Отдельное расписание автомобилей и обмен
ресурсами между инженерами пока не моделируются.

### `EngineerAvailability`

```python
EngineerAvailability(
    engineer_id="e1",
    available_from="08:00",
    available_until="17:00",
)
```

Оба значения задаются как `HH:MM`, например `"08:00"` и `"17:00"`.

### `Task`

```python
Task(
    id="t1",
    location_id="customer-1",
    required_skills=frozenset({Skill.LOCAL_WORKS}),
    required_equipment=frozenset({"multimeter"}),
    required_vehicle_type=VehicleType.CAR,
    duration_minutes=30,
    window_start="09:00",
    window_end="12:00",
    priority=Priority.NORMAL,
)
```

`window_start` и `window_end` задают жёсткое окно визита и
относятся к началу обслуживания. `priority` принимает значения `NORMAL` и
`URGENT` и влияет на штраф за неназначение.
Длительность работы прибавляется после начала обслуживания.

### `RouteStop` и `EngineerRoute`

`RouteStop` хранит расписание одной заявки:

- `arrival_time` — прибытие после переезда от предыдущей точки;
- `service_start_time` — начало работы с заявкой;
- `service_end_time` — окончание работы;
- `travel_time_from_previous` — длительность последнего переезда.

Если инженер приехал раньше окна, `service_start_time` будет позже
`arrival_time`. Разница между ними — ожидание.

`EngineerRoute.stops` — упорядоченный кортеж остановок. Поле
`total_travel_minutes` включает путь от базы до первой заявки и переезды между
заявками. Путь после последней заявки не добавляется. `total_service_minutes` —
сумма длительностей работ.

## Как OR-Tools представляет задачу

Получение матриц отделено от решателя. `RoutingProvider` имеет методы
`get_travel_time_matrix(location_ids, vehicle_type)`,
`get_distance_matrix(location_ids, vehicle_type)` и
`get_route_geometry(location_ids, vehicle_type)`. Первый возвращает минуты,
второй — километры, третий — GeoJSON geometry либо `None`.
`InMemoryRoutingProvider` возвращает подматрицы из заранее переданных данных и
остаётся детерминированным provider для тестов. `OSRMRoutingProvider` вызывает
OSRM Table для двух матриц и OSRM Route для geometry; простой кэш по полному URL
не повторяет одинаковый HTTP-запрос в рамках одного экземпляра provider.
Benchmark и web API передают ему отдельный endpoint для автомобильного,
пешего и велосипедного графа. Это принципиально: строка профиля в URL сама по
себе не превращает автомобильный сервер OSRM в пешеходный. Для
`PUBLIC_TRANSPORT` используется автомобильный граф и множитель времени 2.0,
поскольку стандартный OSRM не моделирует расписания и пересадки.
`ORToolsOptimizer` получает только готовый `OptimizationProblem` и не знает,
какой источник построил матрицы.

Внутри `RoutingModel` задача представлена графом. Узлы — стартовые точки
инженеров и локации заявок, дуги — возможные переходы. Каждый OR-Tools
`vehicle` в этой модели соответствует одному инженеру и означает его маршрут.
Это внутренний термин OR-Tools, а не ссылка на физический автомобиль
`VehicleResource`.

Для каждого инженера OR-Tools технически создаёт цепочку от стартового узла к
конечному узлу. Локация начала и конца задаётся одинаково, как того требует
интерфейс `RoutingIndexManager`, но переход в технический конечный узел имеет
нулевую стоимость. Поэтому в предметной модели маршрут начинается в базе и
заканчивается на последней заявке: возвращение в базу не считается.
Узлы заявок создаются отдельно от стартовых узлов. Две заявки
могут иметь один `location_id`: для OR-Tools это два разных посещения, но
время движения берётся из одной локации матрицы.

Это задача Vehicle Routing Problem (VRP) с временными окнами (VRPTW) и
ограничениями на допустимость инженера.

## Пошаговая работа `optimize`

### 1. Проверка допустимости назначения

`_has_eligible_engineer` проверяет каждую заявку до создания модели OR-Tools.
Упрощённо проверка выглядит так:

```python
task.required_skills.issubset(engineer.qualifications)
and task.required_equipment.issubset(effective_equipment)
and (
    task.required_vehicle_type is None
    or effective_vehicle_type == task.required_vehicle_type
)
```

Здесь `effective_equipment` включает простое поле `engineer.available_equipment` и типы
закреплённых за инженером `EquipmentResource`, а `effective_vehicle_type`
берётся из `VehicleResource`, если транспортный экземпляр закреплён. Это
сокращённая запись; полный расчёт выполняет `_engineer_can_execute_task`.

Если ни один инженер не подходит по жёстким ограничениям, заявка не
добавляется в модель OR-Tools. Если у инженеров нет нужных навыков, причина —
`missing_qualification`. Если квалификация подходит, но нет полного набора
оборудования, причина — `missing_equipment`. Если навыки и оборудование
подходят, но нет
нужного типа транспорта, причина — `missing_vehicle_type`. Это позволяет
построить маршруты для остальных заявок и явно вернуть невозможную заявку в
результате.

### 2. Подключение OR-Tools

В Python пакет OR-Tools подключается так:

```python
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
```

[`pywrapcp`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html)
— это Python-обёртка над C++-библиотекой Constraint Solver из Google OR-Tools.
Через этот модуль Python получает доступ к классам маршрутизации и
ограничений. `pywrapcp` — не отдельный алгоритм и не отдельный решатель: это
мост между Python-кодом и встроенной C++-реализацией OR-Tools.

`routing_enums_pb2` содержит перечисления, сгенерированные из protobuf. В
текущем коде из него используется
`FirstSolutionStrategy.PATH_CHEAPEST_ARC` — способ построить первое решение.

Полезные официальные материалы:

- [Общие задачи маршрутизации OR-Tools](https://developers.google.com/optimization/routing/routing_tasks?hl=ru);
- [VRP с временными окнами](https://developers.google.com/optimization/routing/vrptw?hl=ru);
- [Измерения маршрута и slack](https://developers.google.com/optimization/routing/dimensions?hl=ru);
- [Настройки поиска](https://developers.google.com/optimization/routing/routing_options?hl=ru);
- [Ограничения ресурсов](https://developers.google.com/optimization/routing/cvrptw_resources?hl=ru);
- [Python API модуля `pywrapcp`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html).

### 3. `RoutingIndexManager`: узлы и внутренние индексы

[`RoutingIndexManager`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#RoutingIndexManager)
— встроенный класс Google OR-Tools. Он переводит логические номера узлов в
индексы, которыми пользуется `RoutingModel`.

В проекте он создаётся так:

```python
manager = pywrapcp.RoutingIndexManager(
    len(node_location_ids),
    engineer_count,
    starts,
    starts,
)
```

Здесь существуют два вида индексов.

1. **Логический индекс узла** — позиция в нашем списке
   `node_location_ids`. По нему мы связываем узел с `location_id` и матрицей.
2. **Внутренний индекс маршрутизации** — индекс переменной внутри
   `RoutingModel`. Его получает и использует OR-Tools.

Эти индексы нельзя бездумно считать одинаковыми. Внутри модели есть
специальные start/end-узлы маршрутов, а внутренние индексы могут отличаться от
обычных индексов строк матрицы. Поэтому callback сначала вызывает
`manager.IndexToNode(...)`, а уже потом обращается к нашим данным.

#### Что означают четыре аргумента

Конструктор удобно читать в таком виде:

```python
RoutingIndexManager(
    number_of_nodes,
    number_of_vehicles,
    starts,
    ends,
)
```

| Аргумент | Значение в проекте | Что означает |
|---|---:|---|
| `number_of_nodes` | `len(node_location_ids)` | Число логических узлов: стартовые узлы инженеров плюс узлы заявок. |
| `number_of_vehicles` | `engineer_count` | Число маршрутов. В нашей модели один vehicle соответствует одному инженеру. |
| `starts` | `[0, 1, 2]` для трёх инженеров | Логический узел начала каждого маршрута. Позиция в списке соответствует номеру vehicle. |
| `ends` | В коде снова `starts` | Технический конечный узел каждого маршрута. Позиция также соответствует номеру vehicle. |

`starts` передаётся два раза из-за API OR-Tools. Третий параметр задаёт начала
маршрутов, а четвёртый — технические концы. В callback переход к конечному
индексу имеет нулевое время и нулевое расстояние, поэтому возвращение к
стартовой локации не моделируется:

```python
starts = [0, 1, 2]
ends = [0, 1, 2]
```

Это означает:

```text
vehicle 0: base-1 → заявки → конец маршрута
vehicle 1: base-2 → заявки → конец маршрута
vehicle 2: base-3 → заявки → конец маршрута
```

Если бы все инженеры начинали и заканчивали в одном общем депо с логическим
узлом `0`, вызов выглядел бы иначе:

```python
starts = [0, 0, 0]
ends = [0, 0, 0]
```

В нашем коде список `node_location_ids` начинается со стартовых локаций
инженеров, поэтому `starts = [0, 1, 2]` указывает именно на три разные базы.

#### Преобразование индексов

`IndexToNode` переводит внутренний индекс OR-Tools в логический индекс:

```python
from_node = manager.IndexToNode(from_index)
to_node = manager.IndexToNode(to_index)
```

`NodeToIndex` выполняет обратное преобразование для обычного логического узла:

```python
task_index = manager.NodeToIndex(task_node)
```

В коде проекта первое преобразование используется в callback’ах, а второе —
при настройке ограничений конкретной заявки и при чтении решения.

Официальное объяснение роли менеджера и start/end-массивов есть в разделе
[общих задач маршрутизации OR-Tools](https://developers.google.com/optimization/routing/routing_tasks?hl=ru).

### 4. `RoutingModel`: модель маршрутов

После менеджера создаётся
[`RoutingModel`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#RoutingModel):

```python
routing = pywrapcp.RoutingModel(manager)
```

`RoutingModel` — встроенный класс Google OR-Tools для задач маршрутизации
транспортных средств (Vehicle Routing Problem). Он хранит переменные
маршрутов, ограничения и стоимость переходов, а также запускает поиск
решения.

В текущем решателе используются следующие методы и переменные:

- `routing.Start(vehicle_index)` — внутренний индекс начала маршрута;
- `routing.End(vehicle_index)` — внутренний индекс конца маршрута;
- `routing.NextVar(index)` — переменная следующего узла;
- `routing.VehicleVar(index)` — индекс маршрута, которому назначен узел. В
  текущем проекте этот индекс соответствует инженеру;
- `routing.ActiveVar(index)` — посещается ли необязательный узел;
- `routing.RegisterTransitCallback(...)` — регистрация Python-функции перехода;
- `routing.SetArcCostEvaluatorOfAllVehicles(...)` — выбор стоимости дуг для
  всех vehicle;
- `routing.SolveWithParameters(...)` — запуск поиска.

Цепочка `NextVar` описывает порядок маршрута. Например:

```text
Start(0) → заявка t3 → заявка t1 → End(0)
```

В терминах OR-Tools `VehicleVar` отвечает на вопрос, какому маршруту
принадлежит узел. В проекте маршруты сопоставлены инженерам по позиции в
`problem.engineers`: `vehicle_index == 0` — первый инженер,
`vehicle_index == 1` — второй и так далее.
Поэтому назначение и порядок определяются одной моделью, а не двумя
последовательными программными шагами.

### 5. Callback стоимости движения

Матрица приходит извне через `OptimizationProblem`. Сам решатель её не
строит.
Для чтения времени движения регистрируется callback:

```python
def travel_time_callback(from_index: int, to_index: int) -> int:
    from_node = manager.IndexToNode(from_index)
    to_node = manager.IndexToNode(to_index)
    from_location = node_location_ids[from_node]
    to_location = node_location_ids[to_node]
    return problem.travel_time_matrix[from_location][to_location]

transit_callback_index = routing.RegisterTransitCallback(
    travel_time_callback
)
routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
```

[`RegisterTransitCallback`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#RoutingModel.RegisterTransitCallback)
регистрирует функцию и возвращает не саму стоимость, а числовой идентификатор
callback’а. OR-Tools использует этот идентификатор внутри модели.

На каждом переходе callback:

1. получает внутренние индексы `from_index` и `to_index`;
2. переводит их в логические индексы через `RoutingIndexManager`;
3. получает `location_id` из `node_location_ids`;
4. читает минуты движения из готовой матрицы.

[`SetArcCostEvaluatorOfAllVehicles`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#RoutingModel.SetArcCostEvaluatorOfAllVehicles)
говорит модели использовать эту стоимость для каждого инженера. В маршрут
входят переезды:

```text
base → первая заявка
+ заявка → следующая заявка
+ последняя заявка → base
```

Длительность обслуживания не входит в этот callback. Она учитывается отдельно
в календарном callback’е, потому что текущая целевая функция выделяет время
движения в отдельный компонент.

Callback возвращает исходное время движения в минутах. Поле
`OptimizerConfig.travel_time_penalty_per_minute` применяется при сборке
`OptimizationResult.travel_time_penalty`; при стандартном весе `1` это то же
самое значение. Поэтому изменение этого веса сейчас меняет метрику результата,
но не меняет arc cost внутри поиска `RoutingModel`.

### 6. Жёсткие ограничения назначения

До добавления заявок в модель проверяется, существует ли хотя бы один
подходящий инженер. Инженер должен одновременно удовлетворять требованиям к
навыкам, оборудованию и транспорту:

```python
task.required_skills.issubset(engineer.qualifications)
and task.required_equipment.issubset(available_equipment)
and (
    task.required_vehicle_type is None
    or available_vehicle_type == task.required_vehicle_type
)
```

Для заявок, которые прошли эту предварительную проверку, из домена
`VehicleVar` удаляются маршруты, соответствующие неподходящим инженерам:

```python
if not self._engineer_can_execute_task(problem, engineer, task):
    routing.VehicleVar(task_index).RemoveValue(vehicle_index)
```

[`RemoveValue`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#IntVar.RemoveValue)
удаляет конкретное значение из множества допустимых значений переменной. Это
не штраф и не рекомендация: после удаления OR-Tools физически не может
назначить заявку этому инженеру.

Например, если:

```text
e1: skills={LOCAL_WORKS}, available_equipment={multimeter}, vehicle_type=CAR
e2: skills={LOCAL_WORKS}, available_equipment={}, vehicle_type=WALK
t1: required_skills={LOCAL_WORKS}, required_equipment={multimeter},
    required_vehicle_type=CAR
```

то для `t1` остаётся только `e1`.

### 7. Ограниченные экземпляры оборудования и транспорта

Простые поля `Engineer.available_equipment` и `Engineer.vehicle_type` продолжают
поддерживаться. Если нужно различать экземпляры, используются
`EquipmentResource` и `VehicleResource`:

```python
equipment_resources = (
    EquipmentResource(id="meter-1", equipment_type="multimeter"),
    EquipmentResource(id="meter-2", equipment_type="multimeter"),
)
vehicle_resources = (
    VehicleResource(id="car-1", vehicle_type="CAR"),
)
```

Инженер ссылается на закреплённые экземпляры:

```python
Engineer(
    id="e1",
    name="Анна",
    qualifications=frozenset({Skill.LOCAL_WORKS}),
    start_location_id="base",
    vehicle_type=VehicleType.CAR,
    equipment_resource_ids=frozenset({"meter-1"}),
    vehicle_resource_id="car-1",
)
```

Количество экземпляров задаётся количеством объектов в соответствующем
списке. `OptimizationProblem` проверяет, что ссылки инженеров указывают на
существующие ресурсы.

Если один экземпляр указан у нескольких инженеров, текущий решатель запрещает
пересечение их сервисных интервалов. Для этого он создаёт булевы переменные
через
[`IsEqualCstVar`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#Solver.IsEqualCstVar),
связывает их с `ActiveVar` и `VehicleVar`, а затем для каждой пары
использований задаёт один из двух вариантов порядка:

```text
service_end(A) <= service_start(B)
или
service_end(B) <= service_start(A)
```

[`AddVariableMinimizedByFinalizer`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#RoutingModel.AddVariableMinimizedByFinalizer)
фиксирует служебные булевы переменные при завершении поиска. Отдельное
расписание автомобилей и динамическое распределение транспорта между
инженерами пока не создаются.

### 8. Календарный callback

Для проверки времени регистрируется второй callback:

```python
def schedule_time_callback(from_index: int, to_index: int) -> int:
    from_node = manager.IndexToNode(from_index)
    to_node = manager.IndexToNode(to_index)
    from_location = node_location_ids[from_node]
    to_location = node_location_ids[to_node]
    task_at_from = task_by_node.get(from_node)
    service_duration = (
        task_at_from.duration_minutes if task_at_from is not None else 0
    )
    return (
        problem.travel_time_matrix[from_location][to_location]
        + service_duration
    )
```

В этом фрагменте показаны все необходимые преобразования: сначала OR-Tools
передаёт внутренние индексы, затем `RoutingIndexManager` переводит их в наши
узлы, а `node_location_ids` — в идентификаторы локаций.

Переход после заявки `A` к заявке `B` поэтому занимает:

```text
duration(A) + travel_time(A, B)
```

Для перехода от базы к первой заявке длительность обслуживания равна нулю.
Переход от последней заявки к конечной базе включает работу последней заявки.
Так календарная цепочка не позволяет начать следующую заявку до окончания
предыдущей.

### 9. `RoutingDimension` и `AddDimension`

Для накопления времени создаётся
[`RoutingDimension`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#RoutingDimension):

```python
routing.AddDimension(
    schedule_callback_index,
    time_horizon,
    time_horizon,
    False,
    "Time",
)
time_dimension = routing.GetDimensionOrDie("Time")
```

[`AddDimension`](https://developers.google.com/optimization/routing/dimensions?hl=ru)
создаёт для маршрутов набор переменных, связанных формулой перехода.
Основные понятия:

- **transit** — значение callback для перехода;
- **slack** — дополнительное ожидание между узлами;
- **cumul** — накопленное значение на узле, доступное через `CumulVar`.

Параметры вызова в проекте:

| Параметр | Значение | Смысл |
|---|---|---|
| `transit_callback_index` | `schedule_callback_index` | Callback, возвращающий движение плюс работу в исходном узле. |
| `slack_max` | `time_horizon` | Максимальное ожидание на переходе. Большое значение позволяет дождаться окна. |
| `capacity` | `time_horizon` | Верхняя граница накопленного времени. |
| `fix_start_cumul_to_zero` | `False` | Начало маршрута не принудительно равно нулю. |
| `dimension_name` | `"Time"` | Имя измерения для `GetDimensionOrDie`. |

Значение `False` позволяет установить начало каждого маршрута в
`available_from`, например в `"08:00"` на границе доменной модели или в
`480` минут внутри решателя.

Для соседних узлов действует формула:

```text
cumul(next) = cumul(current)
             + transit(current, next)
             + slack(current)
```

Если инженер приехал в минуте 50, а окно начинается в минуте 300, slack
может равняться 250 минутам.

### 10. Рабочее время инженера

Для начала и конца маршрута задаются границы через
[`CumulVar`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#RoutingDimension.CumulVar)
и `SetRange`:

```python
time_dimension.CumulVar(start_index).SetRange(
    hhmm_to_minutes(availability.available_from),
    hhmm_to_minutes(availability.available_from),
)
time_dimension.CumulVar(end_index).SetRange(
    hhmm_to_minutes(availability.available_from),
    hhmm_to_minutes(availability.available_until),
)
```

Первый вызов фиксирует начало смены. Второй ограничивает момент окончания
последней работы. Следовательно, в рабочий интервал должны поместиться путь до
первой заявки, ожидание, работы и переезды до последней заявки.

Выход за смену — жёсткое ограничение. Он не превращается в штраф за
сверхурочную работу и не разрешается ради более короткого маршрута.

### 11. Жёсткие временные окна

Для заявки задаётся диапазон времени начала обслуживания:

```python
time_dimension.CumulVar(task_index).SetRange(
    hhmm_to_minutes(task.window_start),
    hhmm_to_minutes(task.window_end),
)
```

[`SetRange`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#IntExpr.SetRange)
не допускает значение вне указанного диапазона. `visit_window` — это жёсткое
ограничение, поэтому решатель не может компенсировать его нарушение штрафом.

Пример:

```text
начало смены       = 0
время движения     = 50
arrival_time       = 50
начало окна        = 300
service_start_time = 300
duration           = 100
service_end_time   = 400
```

Инженер приехал раньше и подождал. Если приехать вовремя невозможно, заявка
становится неназначенной с причиной `impossible_time_window`. Если начать в
окне можно, но работа не помещается в смену, причина —
`outside_working_hours`.

### 12. SLA не входит в текущую модель

В текущем официальном контракте `Task` нет полей `service_deadline` и SLA.
Решатель не принимает и не обрабатывает эти значения. Если SLA потребуется
позже, его следует добавить отдельным расширением domain-модели и целевой
функции, не смешивая его с жёстким `window_start`/`window_end`.

### 13. Неназначаемые заявки и `AddDisjunction`

Заявка, прошедшая жёсткие ограничения ресурсов, добавляется как
необязательный узел:

```python
routing.AddDisjunction(
    [task_index],
    config.unassigned_penalty * config.unassigned_multiplier(task),
)
```

[`AddDisjunction`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#RoutingModel.AddDisjunction)
разрешает модели не посещать узел и заплатить штраф. Это нужно, чтобы
невозможность выполнить одну заявку по времени не делала всю задачу
нерешаемой.

Разница между механизмами такая:

- `VehicleVar(...).RemoveValue(...)` запрещает конкретного инженера;
- `CumulVar(...).SetRange(...)` запрещает недопустимое время;
- `AddDisjunction(...)` разрешает отказаться от всей заявки за штраф.

Публичный справочник по-прежнему содержит только `NORMAL` и `URGENT`, однако
официальный порядок важности детальнее: авария → подключение → ремонт/дозаказ.
Поэтому `Task` также хранит `work_type`, а `OptimizerConfig` задаёт отдельные
множители штрафа за неназначение:

```python
emergency_unassigned_multiplier = 4
connection_unassigned_multiplier = 2
local_unassigned_multiplier = 1
equipment_order_unassigned_multiplier = 1
```

Эти коэффициенты используются только тогда, когда заявку приходится оставить
неназначенной. Они не заставляют solver ставить подключение раньше ремонта в
одном допустимом маршруте. Для старых объектов `Task` без `work_type` сохранён
fallback через `normal_unassigned_multiplier` и
`urgent_unassigned_multiplier`.

### 14. Настройки поиска

После построения модели создаётся объект параметров поиска:

```python
search_parameters = pywrapcp.DefaultRoutingSearchParameters()
search_parameters.first_solution_strategy = (
    routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
)
search_parameters.time_limit.FromTimedelta(
    timedelta(minutes=self.config.time_limit_minutes)
)
```

[`DefaultRoutingSearchParameters`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#DefaultRoutingSearchParameters)
возвращает настройки по умолчанию. В текущем решателе изменяются два параметра.

- `first_solution_strategy` задаёт способ построить первое допустимое решение.
- `time_limit` задаёт максимальное время поиска.

`PATH_CHEAPEST_ARC` начинает с дешёвых дуг по стоимости callback’а движения. Это
эвристика первого решения, а не математическое доказательство глобального
оптимума.

### 15. Запуск `SolveWithParameters`

Поиск запускается так:

```python
solution = routing.SolveWithParameters(search_parameters)
```

[`SolveWithParameters`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#RoutingModel.SolveWithParameters)
запускает решатель маршрутизации с заданными параметрами и возвращает
[`Assignment`](https://or-tools.github.io/docs/pdoc/ortools/constraint_solver/pywrapcp.html#Assignment)
с найденными значениями переменных.

```python
OptimizerConfig(time_limit_minutes=5)
```

означает лимит поиска 5 минут. Лимит ограничивает поиск, но не гарантирует,
что найденное решение является глобально лучшим.

Если `solution is None`, OR-Tools не смог построить допустимое решение модели
вообще, и текущий код выбрасывает `ValueError`. Невозможность одной заявки
обычно не приводит к этому случаю, потому что заявка необязательна и может быть
снята через `AddDisjunction`.

### 16. Как одновременно выбираются инженер и порядок

Рассмотрим заявки `A` и `B`.

1. Для каждой заявки из домена `VehicleVar` удаляются индексы маршрутов,
   соответствующие инженерам без нужных навыков, оборудования или транспорта.
2. `RoutingModel` выбирает, будет ли заявка активной.
3. `VehicleVar` выбирает маршрут, то есть инженера.
4. `NextVar` выбирает положение заявки в цепочке этого инженера.
5. `Time` проверяет окна, ожидание и рабочую смену.
6. Штраф за неназначение влияет на стоимость решения.

Для одного инженера возможны два порядка:

```text
base → A → B
base → B → A
```

Компоненты времени движения в минутах для этих вариантов равны:

```text
travel(base, A) + travel(A, B)
travel(base, B) + travel(B, A)
```

Решатель выбирает допустимый вариант с меньшей итоговой стоимостью. Поэтому
он не назначает заявки отдельно от порядка: назначение и последовательность
являются переменными одной VRP-модели.

### 17. Чтение `Assignment` и построение результата

Маршрут каждого инженера читается от `Start` до `End`:

```python
index = routing.Start(vehicle_index)
while not routing.IsEnd(index):
    next_index = solution.Value(routing.NextVar(index))
    index = next_index
```

`solution.Value(...)` читает значение переменной из найденного
`Assignment`.

Если `next_index` соответствует заявке, начало обслуживания берётся из
временного измерения:

```python
service_start_time = solution.Value(
    time_dimension.CumulVar(next_index)
)
```

Затем `_build_engineer_route` формирует поля `RouteStop`:

```text
arrival_time     = предыдущее доступное время + travel(previous, current)
service_start    = значение CumulVar заявки
service_end      = service_start + duration_minutes
```

Разница между `arrival_time` и `service_start_time` — ожидание. Переезд после
последней заявки к базе не моделируется и не входит в метрики.

Для необязательной заявки проверяется:

```python
solution.Value(routing.ActiveVar(task_index)) == 0
```

Такая заявка попадает в `unassigned_task_ids`, а причина определяется отдельно:
квалификация, оборудование, транспорт, окно или рабочее время.

### 18. Разложение objective

Целевая функция текущего OR-Tools solver’а состоит из четырёх компонентов:

```text
unassigned_penalty      = Σ(штраф заявки × множитель приоритета)
used_engineers_penalty  = used_engineers_count × config.used_engineers_penalty
distance_penalty        = total_distance × config.distance_penalty_per_km
travel_time_penalty     = total_travel_time × config.travel_time_penalty_per_minute

total_objective = unassigned_penalty
                + used_engineers_penalty
                + distance_penalty
                + travel_time_penalty
```

Вес неназначения должен быть самым большим, затем идёт стоимость инженера,
расстояния и времени движения. Так допустимые решения сравниваются сначала по
числу выполненных заявок, затем по числу инженеров, затем по расстоянию и
только после этого по travel time. Жёсткие ограничения не входят в формулу:
нарушить их нельзя.

`OptimizationResult` хранит эти компоненты отдельно и проверяет, что их сумма
равна `total_objective`. SLA и overtime-компоненты в актуальной модели
отсутствуют.

### 19. Почему заявка стала неназначенной

Причина зависит от этапа, на котором заявка стала невозможной.

#### `missing_qualification`

Ни один инженер не покрывает `required_skills`. Заявка исключается до
создания узла OR-Tools.

#### `missing_equipment`

Квалифицированные инженеры есть, но ни у одного нет всего
`required_equipment`.

#### `missing_vehicle_type`

Навыки и оборудование подходят, но ни один инженер не имеет нужного
`vehicle_type` или закреплённого `VehicleResource` соответствующего типа.

#### `impossible_time_window`

Инженер подходит по ресурсам, но не может начать работу внутри
`window_start`/`window_end` с учётом движения от базы.

#### `outside_working_hours`

Начать работу в окне возможно, но работа не помещается в доступный интервал.
Сюда же относится заявка, которая отдельно помещается, но не помещается
вместе с другими заявками выбранного маршрута.

### 20. Разбор тестов

Тесты находятся в
`backend/optimization/tests/test_ortools_optimizer.py`.

#### Ожидание начала окна

Смена равна `08:00..17:00`, движение занимает 10 минут, окно начинается в
`10:00`, длительность работы равна 30 минутам. Инженер приезжает в `08:10`,
ждёт до `10:00` и заканчивает в `10:30`.

#### Невозможное окно

Движение занимает 10 минут, а окно заканчивается в `08:05`. Заявка
снимается через `AddDisjunction` и получает `impossible_time_window`.

#### Выход за смену

Десять минут движения до заявки, 5 минут работы и 10 минут обратно
требуют 25 минут при смене длиной 20 минут. Заявка получает
`outside_working_hours`.

#### Несколько заявок

Один инженер получает две заявки. `NextVar` выбирает порядок, а календарный
callback учитывает работу первой заявки до начала второй.

#### Навыки, оборудование и транспорт

Тесты проверяют допустимое и недопустимое назначение по каждому жёсткому
ограничению, включая случай без `required_vehicle_type`.

#### Один общий экземпляр

Два инженера с разными навыками ссылаются на один `EquipmentResource`. Каждая
заявка закрепляется за своим инженером, но сервисные интервалы не пересекаются:

```text
end(A) <= start(B)
или
end(B) <= start(A)
```

#### Приоритет

`Priority.NORMAL` и `Priority.URGENT` остаются внешним контрактом. Основной
штраф за неназначение определяется `WorkType`: авария имеет вес 4, подключение
— 2, ремонт и дозаказ — 1. Это выбирает более важную заявку при нехватке
ресурсов, но не вводит обязательный порядок посещения. Сроки SLA в текущем
алгоритме отсутствуют.

### 21. Benchmark и запуск

Из корня проекта:

```bash
.venv/bin/python -m pytest backend/optimization -q
.venv/bin/python -m backend.optimization.benchmarks.benchmark_ortools
.venv/bin/python -m backend.optimization.benchmarks.benchmark_ortools_large --iterations 1
```

Benchmark использует `InMemoryRoutingProvider` и заранее передаёт
детерминированную матрицу в `OptimizationProblem`. Построение исходных данных
не смешивается с измеряемым вызовом `optimize`.

Benchmark не является тестом производительности с порогом. После прогрева он
выполняет заданное число запусков и печатает среднее, медиану, минимум и
максимум времени решения.

### 22. Короткая математическая постановка

Пусть `x(i, j, v)` равно 1, если инженер `v` едет из узла `i` в узел `j`.
Пусть `y(t, v)` равно 1, если заявка `t` назначена инженеру `v`, а `z(t)`
равно 1, если заявка обслужена.

Базовая часть целевой функции, связанная со временем движения в минутах:

```text
Σ_v Σ_i Σ_j travel_time(i, j) × x(i, j, v)
```

Штраф за неназначенные заявки:

```text
Σ_t (1 - z(t)) × unassigned_penalty × work_type_multiplier(t)
```

При этом действуют жёсткие ограничения:

```text
каждая заявка либо назначена одному инженеру, либо снята как необязательная;
назначение разрешено только при совместимых навыках, оборудовании и транспорте;
для каждого инженера выбранная последовательность начинается в start и
заканчивается на последней заявке;
время начала заявки попадает в visit_window;
время конца маршрута попадает в рабочий интервал инженера;
сервисные интервалы одного экземпляра ресурса не пересекаются.
```

Именно поэтому OR-Tools одновременно определяет назначение, последовательность и
расписание, а `OptimizationResult` показывает маршрут, ожидание и причину
неназначения.

### 23. `GreedyBaselineOptimizer`

Baseline нужен для сравнения с глобальным решателем. Он использует тот же
`OptimizationProblem`, обе внешние матрицы и те же жёсткие ограничения, но не
создаёт модель OR-Tools и не ищет оптимум.

Алгоритм последовательно берёт заявки из `problem.tasks`. Для каждой заявки он
перебирает инженеров из `problem.engineers` и выбирает первого, для которого
подходят навыки, оборудование, транспорт, временное окно, смена и доступность
ограниченных ресурсов. Новая заявка добавляется в конец маршрута инженера.
Поэтому порядок заявок в его маршруте совпадает с порядком назначения.

`GreedyBaselineOptimizer` возвращает тот же `OptimizationResult`, включая
`distance_by_engineer`, `total_distance`, `travel_time_by_engineer`,
`total_travel_time`, `used_engineers_count` и счётчики назначенных и
неназначенных заявок. Его результат может быть допустимым, но хуже результата
`ORToolsOptimizer`, потому что раннее жадное назначение уже не пересматривается.

### 24. Ручное планирование и контрольный CSV

Ручные назначения находятся в `manual_planner.py` и являются частью
Optimization Engine. Отдельного одноразового скрипта для проверки dataset нет.
Это позволяет позже вызвать ту же функцию из API или веб-интерфейса.

`ManualAssignmentPlan` хранит назначение заявки инженеру и порядок посещения.
Метод `add_task(problem, engineer_id, task_id)` сначала делает копию плана,
добавляет в неё заявку и вызывает `ManualAssignmentPlanner.validate`. Изменение
сохраняется только при полном соблюдении hard constraints. При ошибке
выбрасывается `ManualAssignmentError`, а его поле `violations` содержит
структурированный код и сообщение для каждой причины.

Проверяются квалификация, оборудование, транспорт, временное окно, смена и
конфликт отдельных экземпляров ресурсов. Для активной заявки сначала
прибавляется время движения, затем берётся максимум из времени прибытия и
начала окна — это начало обслуживания. Отменённая заявка сохраняется в
контрольном распределении, но не занимает ни времени, ни ресурса. Поэтому
следующая заявка может иметь то же окно после отмены.

`load_control_dataset` загружает CSV с разделителем `;`, сопоставляет номер
заявки и имя бригады с `JsonScenario`, а также сверяет статус и окно с JSON.
CSV заказчика содержит исполнителя, но не содержит порядок визитов. Для
проверки расписания benchmark передаёт заявки в `ControlDataset.plan(tasks)`:
внутри каждого инженера они сортируются по началу окна, а порядок строк CSV
используется для одинаковых окон. Если такой план нарушает жёсткое ограничение,
`optimize` не создаёт ложный допустимый результат, а benchmark печатает число и
коды нарушений.

Третий вариант benchmark — «Контрольное распределение (составители)». Его
расстояния, если план допустим, берутся из той же routing matrix по фактическому
типу транспорта инженера. Для OSRM это дорожное расстояние выбранного профиля;
для `PUBLIC_TRANSPORT` текущий provider использует профиль `driving` как явное
допущение OSRM и умножает время движения на 2.0.

Запуск сравнения с OSRM:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider osrm --iterations 1
```
