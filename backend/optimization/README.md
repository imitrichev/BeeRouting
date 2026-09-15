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

Benchmark крупного сценария (15 инженеров, 100 заявок):

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_ortools_large --iterations 1
```

Количество измерений можно изменить параметром `--iterations N`. Benchmark
не содержит порога времени и не влияет на результат unit-тестов.
