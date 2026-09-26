# Optimization Engine

`backend/optimization` — независимое от Django математическое ядро BeeRouting.
Его можно импортировать из Python без запуска web-приложения.

В пакете находятся:

- dataclass-модели инженеров, заявок, смен, маршрутов и результата;
- `RoutingProvider` и детерминированные in-memory/coordinate provider’ы;
- `OSRMRoutingProvider` для дорожных матриц и GeoJSON geometry;
- `ORToolsOptimizer` — основной VRPTW solver;
- `GreedyBaselineOptimizer` — базовый алгоритм из ТЗ;
- `ICOOptimizer` — экспериментальный ICO-DE solver с random keys;
- `TimefoldOptimizer` — необязательный solver для сравнения;
- импорт JSON, генератор датасетов из CSV и объяснение результатов.

## Быстрый пример

```python
from backend.optimization import OptimizerConfig, ORToolsOptimizer

result = ORToolsOptimizer(
    OptimizerConfig(time_limit_minutes=1)
).optimize(problem)

print(result.used_engineers_count)
print(result.total_distance)
print(result.unassigned_task_ids)
```

`problem` должен содержать обе внешние матрицы: travel time в минутах и
distance в километрах. Если переданы профильные матрицы, solver выбирает их по
`engineer.vehicle_type`. Внутренние бизнес-правила не зависят от OSRM.

Hard constraints: квалификация, тип транспорта, опциональное оборудование,
временное окно, смена, фиксированные начатые заявки и конфликты отдельных
ресурсов. В результате доступны маршруты, неназначенные заявки с причинами,
километраж по инженерам, время движения, число задействованных инженеров и
разложение objective.

Длительности и travel time — минуты, границы времени — `HH:MM`, расстояния —
километры. Возврата в стартовую точку после последней заявки нет.

## Solver’ы

`ORToolsOptimizer` — production-like базовый solver проекта. `Baseline`
назначает заявки по входному порядку и нужен для честного сравнения. `ICO-DE`
и `Timefold` остаются отдельными экспериментальными реализациями и не
подменяют OR-Tools.

Подробное описание OR-Tools, callbacks, `RoutingIndexManager`, временного
измерения, статусов, профильных матриц и objective находится в
[`docs/solver.md`](../../docs/solver.md).

Сравнение solver’ов и все параметры benchmark описаны в
[`docs/benchmarks.md`](../../docs/benchmarks.md).

## Генерация JSON

```bash
.venv/bin/python -m backend.optimization.scripts.generate_dataset_json
```

Источники — синтетический CSV района, корневой `engineers.csv` и необязательный
контрольный CSV. Координаты ищутся в `nominatim_cache.json`, затем в локальном
Nominatim на `127.0.0.1:8080`, затем в публичном Nominatim с ограничением
частоты. Готовые сценарии не используются как источник генерации.

## Тесты

```bash
.venv/bin/python -m pytest backend/optimization/tests -q
```

Тесты используют детерминированные provider’ы; сетевой OSRM для них не нужен.
