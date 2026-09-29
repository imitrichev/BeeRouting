# Optimization Engine BeeRouting

`backend/optimization` — независимое от Django математическое ядро BeeRouting.
Пакет получает предметную задачу с готовыми матрицами движения и возвращает
маршруты в доменных моделях Python. В нём нет зависимостей от ORM, HTTP API,
клиентского приложения и LLM.

## Состав пакета

| Модуль | Назначение |
|---|---|
| `models.py` | Инженеры, заявки, смены, ресурсы, маршруты, причины неназначения и результат |
| `interfaces.py` | Общий интерфейс `RouteOptimizer` |
| `config.py` | Лимиты решателя и численные веса целевой функции |
| `constraints.py` | Общие проверки навыков, транспорта, оборудования и доступности |
| `ortools_optimizer.py` | Основной VRPTW-решатель на Google OR-Tools |
| `baseline_optimizer.py` | Жадный baseline из ТЗ без глобального поиска |
| `ico_optimizer.py`, `ico_de.py` | Экспериментальный ICO-DE-решатель со случайными ключами |
| `timefold_optimizer.py` | Необязательный решатель Timefold для сравнения |
| `manual_planner.py` | Проверка и расчёт заданных вручную маршрутов |
| `routing_provider.py` | In-memory, coordinate и OSRM-провайдеры |
| `osrm_cache.py` | SQLite-кэш пар и NPZ-кэш матриц OSRM |
| `otp_routing.py` | Запросы к OpenTripPlanner и SQLite-кэш ответов |
| `json_import.py` | Преобразование JSON-сценария в доменные модели |
| `explanation.py` | Детерминированные и контрфактические факты для объяснения |
| `work_norms.py` | Нормативы длительности работ |
| `scripts/generate_dataset_json.py` | Генерация районных JSON из CSV |
| `benchmarks/` | Бенчмарки решателей |
| `tests/` | Тесты математического ядра |

Публичные классы и функции экспортируются из `backend.optimization`. Новая
реализация решателя должна соблюдать контракт
`RouteOptimizer.optimize(problem) -> OptimizationResult`.

## Вход и результат

`OptimizationProblem` содержит:

- инженеров, их транспорт и квалификации;
- смену каждого инженера;
- заявки, временные окна, длительность, статус и требования;
- полные матрицы времени в минутах и расстояния в километрах;
- необязательные матрицы для каждого типа транспорта;
- настройки статусов, оборудования и оперативного перепланирования;
- фактические позиции инженеров и остаток начатой работы;
- список недоступных инженеров.

`OptimizationResult` возвращает маршруты, расписание остановок, неназначенные
заявки со структурированными причинами, километраж, время в пути, число
задействованных инженеров и декомпозицию целевой функции:

- `unassigned_penalty`;
- `used_engineers_penalty`;
- `distance_penalty`;
- `travel_time_penalty`;
- `plan_disruption_penalty`;
- `total_objective`.

Все веса и лимиты находятся в `OptimizerConfig`. Жёсткие ограничения не
превращаются в штрафы: недопустимое назначение не попадает в решение.

## Быстрый пример

JSON не содержит дорожных матриц. Сначала сценарий загружается, затем
`RoutingProvider` строит матрицы, после чего запускается решатель:

```python
from backend.optimization import (
    CoordinateRoutingProvider,
    OptimizerConfig,
    ORToolsOptimizer,
    load_json_scenario,
)

scenario = load_json_scenario("Югоцентр.json")
provider = CoordinateRoutingProvider(scenario.location_coordinates)
problem = scenario.to_problem(provider, consider_equipment=True)

result = ORToolsOptimizer(
    OptimizerConfig(time_limit_minutes=1)
).optimize(problem)

print(result.assigned_task_count)
print(result.used_engineers_count)
print(result.total_distance)
print(result.unassigned_reasons)
```

`CoordinateRoutingProvider` предназначен для воспроизводимых тестов и
демонстрации без сети. Он использует расстояние по прямой и средние скорости:
30 км/ч для автомобиля, 15 км/ч для велосипеда, 5 км/ч пешком; общественный
транспорт рассчитывается как автомобильное время, умноженное на два.

## Решатели

### OR-Tools

`ORToolsOptimizer` — основной решатель. Он одновременно выбирает инженера,
порядок заявок и расписание с учётом:

- квалификации и обязательного транспорта;
- оборудования и количества роутеров при `consider_equipment=True`;
- временных окон, дороги, ожидания, длительности работы и смен;
- недоступных инженеров;
- закреплённых начатых заявок и ограниченных экземпляров ресурсов.

Метод также поддерживает принудительное назначение, начальное решение,
эталонные маршруты и отдельный лимит в секундах. Эти возможности используются
для ручного переназначения, объяснений, перепланирования и уточнения матриц.

### Остальные реализации

- `GreedyBaselineOptimizer` перебирает заявки и инженеров во входном порядке и
  выбирает первое допустимое назначение без глобального поиска.
- `ICOOptimizer` кодирует назначение и порядок через random keys, начинает с
  baseline и выполняет экспериментальный островной DE-поиск.
- `TimefoldOptimizer` использует planning list variable и constraint streams.
  Ему требуются отдельное Python-окружение и JDK 17+.
- `ManualAssignmentPlanner` проверяет заранее заданные назначения и порядок
  без запуска OR-Tools; он применяется для контрольных распределений.

Все решатели получают один `OptimizationProblem` и возвращают совместимый
`OptimizationResult`. OR-Tools остаётся основным решателем проекта.

### Объяснение результата

`ExplanationEngine` сначала детерминированно проверяет совместимость и
возможность вставки, затем запускает короткий контрфактический расчёт OR-Tools
для допустимых альтернатив. Результатом являются структурированные факты.
Генерация текста через LLM находится вне Optimization Engine; LLM не принимает
решение о назначении.

## Статусы и перепланирование

По умолчанию:

- `CANCELLED` и `COMPLETED` не входят в новый маршрут;
- `EN_ROUTE` и `IN_PROGRESS` закрепляются за текущим инженером;
- `ASSIGNED` можно перенести;
- `NOT_SENT` и `OVERDUE` участвуют в планировании;
- `preserve_assigned_tasks=True` дополнительно закрепляет `ASSIGNED`;
- `unavailable_engineer_ids` исключает инженеров из назначения.

`ignore_task_statuses=True` нужен для полного утреннего перераспределения:
операционные статусы не фиксируют назначения, и в расчёте участвуют все заявки,
включая `COMPLETED` и `CANCELLED`.

При оперативном перепланировании `planning_time` задаёт начало нового участка
дня, а `EngineerOperationalState` — текущую локацию инженера и остаток
выполняемой работы.

## Маршрутизация

`RoutingProvider` передаёт решателю готовые матрицы и, при наличии координат,
геометрию GeoJSON. Сам решатель не выполняет HTTP-запросы.

- `InMemoryRoutingProvider` работает с заранее подготовленными матрицами;
- `CoordinateRoutingProvider` строит матрицы по haversine;
- `OSRMRoutingProvider` использует OSRM Table и Route, отдельные endpoints и
  профили для автомобиля, ходьбы, велосипеда и общественного транспорта.

OSRM-провайдер кэширует направленные пары в SQLite, целые матрицы в NPZ и
ответы текущего процесса в памяти. Пути задаются через
`OSRM_PAIR_CACHE_PATH` и `OSRM_MATRIX_CACHE_PATH`; `off` и `none` отключают
соответствующий файловый кэш.

Для `PUBLIC_TRANSPORT` базовый fallback — автомобильный OSRM с удвоенным
временем. `OTPRoutingClient` уточняет отдельные фактически используемые дуги
по расписанию OpenTripPlanner. Успешные и пустые ответы кэшируются в SQLite по
координатам, дате и временному интервалу. При сетевой, HTTP- или GraphQL-ошибке
клиент возвращает `None`, и сохраняется fallback.

Цикл «первый запуск OR-Tools → запрос OTP для используемых дуг → обновление
матриц → повторный запуск с начальным решением» выполняется Django-сервисом
планирования, а не математическим ядром. HTTP-запросы внутри callback OR-Tools
не выполняются.

Переменные OSRM и OTP с актуальными значениями перечислены в
[технической документации](../../docs/technical.md#маршрутизация).

## Импорт и генерация данных

`load_json_scenario()` загружает районный JSON, нормализует справочники и
разделяет текущие и контрольные назначения. `JsonScenario.to_problem()`
запрашивает у поставщика матрицы для типов транспорта, реально используемых
инженерами.

Генератор JSON запускается из корня проекта:

```bash
.venv/bin/python -m backend.optimization.scripts.generate_dataset_json
```

Источники — синтетический CSV района, `engineers.csv` и необязательный
контрольный CSV. Адреса и координаты берутся из `nominatim_cache.json` либо
уточняются через Nominatim. Для явного локального endpoint используется:

```bash
.venv/bin/python -m backend.optimization.scripts.generate_dataset_json \
  --nominatim-endpoint http://127.0.0.1:8080/search
```

Формат наборов описан в [документации данных](../../docs/data.md).

## Бенчмарки

Детерминированный запуск для трёх районов:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider coordinate --iterations 1
.venv/bin/python -m backend.optimization.benchmarks.benchmark_vostok \
  --routing-provider coordinate --iterations 1
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_vostok \
  --routing-provider coordinate --iterations 1
```

Для дорожных матриц передайте `--routing-provider osrm`. ICO-DE и Timefold
подключаются флагами `--include-ico-de` и `--include-timefold`. Полный список
параметров приведён в [документации бенчмарков](../../docs/benchmarks.md).

## Тесты

```bash
.venv/bin/python -m pytest backend/optimization/tests -q
```

Тесты используют детерминированные матрицы и подменённые HTTP-ответы, поэтому
реальные OSRM, OTP и Nominatim для обычного прогона не требуются.

Математическая модель и ограничения подробно описаны в
[документации по оптимизации](../../docs/optimization.md).
