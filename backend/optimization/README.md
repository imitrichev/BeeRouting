# Optimization Engine

Независимое от Django математическое ядро BeeRouting. Сейчас поддержан
минимальный VRPTW-сценарий на Google OR-Tools:

- модели `Engineer`, `Task`, `OptimizationProblem`, `OptimizationResult`;
- общий интерфейс `RouteOptimizer`;
- реализация `ORToolsOptimizer`;
- простой `GreedyBaselineOptimizer` без глобального поиска;
- интерфейс `RoutingProvider` и `InMemoryRoutingProvider` для внешней матрицы;
- внешние матрицы времени движения в минутах и расстояния в километрах;
- жёсткие ограничения квалификации, оборудования и типа транспорта;
- временные окна заявок и рабочие интервалы инженеров;
- ожидание до начала временного окна;
- приоритеты `NORMAL` и `URGENT`;
- штраф за неназначение с учётом приоритета;
- минимизация суммарного времени движения по внешней матрице.

## Альтернативный Timefold solver

`TimefoldOptimizer` доступен рядом с `ORToolsOptimizer` и реализует тот же
`RouteOptimizer`. Он принимает существующий `OptimizationProblem`, использует
те же внешние матрицы `RoutingProvider`, проверяет текущие hard constraints и
возвращает тот же `OptimizationResult`. Собственные модели и OSRM-адаптер из
корневого справочного `timef_solver.py` в математическое ядро не переносятся.

Запуск:

```python
from backend.optimization import TimefoldOptimizer

result = TimefoldOptimizer(time_limit_seconds=20).optimize(problem)
```

Если `time_limit_seconds` не передан, используется лимит Timefold 20 секунд.
Это отдельный параметр solver'а: `OptimizerConfig.time_limit_minutes` относится
к лимиту OR-Tools.

Python-пакет Timefold работает через JVM, поэтому для него требуется JDK 17 или
новее и `JAVA_HOME`. Текущая версия Python-пакета поддерживает Python 3.10–3.12;
если основное окружение использует более новый Python, создайте отдельное
`.timefold-venv`. В проекте для него подготовлен OpenJDK 21 из официального
архива OpenJDK. OR-Tools от Java не зависит и остаётся основным solver.
Корневой файл `timef_solver.py` сохранён как справочный материал и не участвует
в импорте установленного пакета.

Граничные времена (`available_from`, `available_until`, `window_start` и
`window_end`) представлены как `HH:MM`. Длительность работ и время движения
задаются в минутах, расстояния — в километрах, координаты — в полях
`latitude` и `longitude`. Внутри OR-Tools время преобразуется в целые минуты.
Маршрут начинается в `start_location_id` инженера и заканчивается на последней
заявке; возвращение на стартовую точку не требуется.

`OptimizationResult` содержит метрики времени и расстояния по каждому инженеру
и суммарно, а также число задействованных инженеров и назначенных заявок.

Установка зависимостей и запуск тестов из корня проекта:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/optimization/requirements.txt
.venv/bin/python -m pytest backend/optimization -q
```

Запуск benchmark текущей производительности:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_ortools
```

Сравнение контрольного плана, Greedy Baseline, OR-Tools и Timefold на
официальном `yugo_center.json`:

```bash
JAVA_HOME="$PWD/.tools/jdk-21.0.2" \
PATH="$JAVA_HOME/bin:$PATH" \
PYTHONPATH="$PWD" \
.timefold-venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider coordinate --iterations 1 --timefold-time-limit-seconds 1
```

В таблице `Timefold` измеряется холодным запуском JVM; для остальных двух
solver'ов сохраняется прежний прогревочный запуск. Это сделано потому, что
повторная инициализация Timefold в одном Python-процессе не даёт надёжного
замера.

Benchmark крупного сценария (15 инженеров, 100 заявок):

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_ortools_large --iterations 1
```

Количество измерений можно изменить параметром `--iterations N`. Benchmark
не содержит порога времени и не влияет на результат unit-тестов.
