# Benchmark

Benchmark — это измерение текущей производительности и качества планов. Это
не unit-тест и в нём нет жёсткого требования «решение обязано работать быстрее
N секунд». Время зависит от CPU, версии OR-Tools, лимита поиска, сети OSRM,
кэша и количества итераций.

Все команды запускаются из корня проекта.

## Окружения

Для Baseline и OR-Tools достаточно основного окружения:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Timefold — отдельная демонстрационная зависимость. Ему нужен совместимый
Python 3.10–3.12, пакет из `backend/optimization/requirements-timefold.txt` и
JDK 17 или новее. Не используйте для него Python 3.14:

```bash
python3.12 -m venv .timefold-venv
.timefold-venv/bin/python -m pip install \
  -r backend/optimization/requirements-timefold.txt
```

Если Java установлена в `PATH`:

```bash
PYTHONPATH="$PWD" \
.timefold-venv/bin/python -m \
  backend.optimization.benchmarks.benchmark_yugo_center \
  --include-timefold
```

Если Java находится в нестандартном каталоге, перед командой задайте
`JAVA_HOME=/path/to/jdk-21` и добавьте `$JAVA_HOME/bin` в `PATH`. Каталог
`.tools/`, который может присутствовать в рабочей копии, локальный и в Git не
хранится; коллега должен использовать системные Python 3.12 и JDK.

Если Java или Python API Timefold недоступны, benchmark печатает причину и
пропускает только Timefold. Baseline и OR-Tools продолжают выполняться.

## Маленький benchmark OR-Tools

Файл: `backend/optimization/benchmarks/benchmark_ortools.py`.

Содержит 3 инженеров и 5 заявок с ручными матрицами. Сеть не используется.
Перед измерениями выполняется один прогревочный запуск.

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_ortools
.venv/bin/python -m backend.optimization.benchmarks.benchmark_ortools \
  --iterations 50
```

Измеряется только `ORToolsOptimizer.optimize()`: импорт JSON, построение
матриц и Django API в это время не входят.

## Крупный детерминированный benchmark

Файл: `backend/optimization/benchmarks/benchmark_ortools_large.py`.

Содержит 15 инженеров и 100 заявок. Матрицы строятся в памяти; benchmark
нужен для наблюдения за ростом времени на более крупной задаче.

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_ortools_large \
  --iterations 1
```

## Сравнительный benchmark «Югоцентр»

Файл: `backend/optimization/benchmarks/benchmark_yugo_center.py`.

Он загружает актуальный `Югоцентр.json`, строит routing data и сравнивает:

1. контрольный план составителей из контрольного CSV;
2. `GreedyBaselineOptimizer`;
3. `ORToolsOptimizer`;
4. `ICOOptimizer`, если указан `--include-ico-de`;
5. `TimefoldOptimizer`, если указан `--include-timefold` и доступна JVM.

Контрольный план не является результатом solver. Заявки из CSV сортируются по
окнам, затем `ManualAssignmentPlanner` проверяет их назначение. Если CSV и
JSON согласованы, но расписание нарушает hard constraint, benchmark показывает
список нарушений и ставит контрольному плану прочерк в сравнительной таблице.
Так недопустимый ручной план не выдаётся за допустимое решение.

Простой запуск без сети:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider coordinate --iterations 1
```

Полное сравнение с двумя дополнительными solver’ами:

```bash
JAVA_HOME="$PWD/.tools/jdk-21.0.2" \
PATH="$JAVA_HOME/bin:$PATH" \
PYTHONPATH="$PWD" \
.timefold-venv/bin/python -m \
  backend.optimization.benchmarks.benchmark_yugo_center \
  --include-ico-de --include-timefold \
  --routing-provider coordinate --iterations 1
```

Benchmark запускает Baseline и OR-Tools всегда. ICO-DE и Timefold выключены
по умолчанию, чтобы обычный запуск оставался коротким.

## Coordinate и OSRM

`--routing-provider coordinate` использует haversine-расстояние между
координатами и демонстрационную скорость. Это расстояние по прямой, а не
дорожный маршрут. Результат воспроизводим и не зависит от сети.

`--routing-provider osrm` использует OSRM Table для времени и расстояния и
OSRM Route для geometry. Профиль выбирается по типу транспорта инженера.
`PUBLIC_TRANSPORT` остаётся приближением: приложение использует автомобильный
граф и удваивает время, потому что обычный OSRM не моделирует расписание и
пересадки общественного транспорта.

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider osrm \
  --iterations 1 \
  --osrm-timeout-seconds 30
```

Параметр OSRM — часть того же benchmark, отдельного файла для OSRM нет.
Время «Импорт и построение матриц» выводится отдельно от времени solver.

## Статусы заявок

По умолчанию benchmark работает в status-aware режиме:

- `CANCELLED` и `COMPLETED` исключаются из нового плана;
- `EN_ROUTE` и `IN_PROGRESS` фиксируются за `current_engineer_id`;
- `ASSIGNED` можно переносить;
- `NOT_SENT` и `OVERDUE` планируются;
- `--preserve-assigned` дополнительно запрещает перенос `ASSIGNED`.

Полный новый план по всем заявкам, включая исторические статусы, запускается
так:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider coordinate --iterations 1 \
  --ignore-task-statuses
```

Это отдельный режим утреннего перераспределения и сравнения solver’ов. В нём
статусы источника не фиксируют заявки.

Учёт количества роутеров включается отдельно:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider coordinate --iterations 1 --consider-equipment
```

## Параметры `benchmark_yugo_center`

| Параметр | По умолчанию | Назначение |
|---|---:|---|
| `--path` | `Югоцентр.json` | JSON-сценарий |
| `--control-csv` | официальный контрольный CSV | Контрольное назначение |
| `--routing-provider` | `coordinate` | `coordinate` или `osrm` |
| `--iterations` | `3` | Число измерений каждого solver’а |
| `--time-limit-minutes` | `1` | Лимит OR-Tools и ICO-DE |
| `--timefold-time-limit-seconds` | `20` | Лимит поиска Timefold |
| `--osrm-timeout-seconds` | `30` | Тайм-аут HTTP-запроса OSRM |
| `--preserve-assigned` | выключен | Фиксировать `ASSIGNED` |
| `--ignore-task-statuses` | выключен | Перестроить план по всем заявкам |
| `--consider-equipment` | выключен | Учитывать запас роутеров |
| `--include-ico-de` | выключен | Добавить ICO-DE |
| `--include-timefold` | выключен | Добавить Timefold при доступной JVM |

`--iterations 1` означает один измеряемый запуск каждого включённого solver’а,
а не «решить только одну заявку». Перед измерениями Baseline и OR-Tools всё
равно выполняется прогревочный запуск. Время Timefold включает холодный запуск
JVM, поэтому его нельзя напрямую сравнивать с чистым временем Python solver.

## Что печатает benchmark

В консоли отображаются:

- источник JSON и routing provider;
- количество инженеров и заявок;
- распределение статусов и состав входа в новый план;
- время импорта и построения матриц;
- время каждого solver’а;
- assigned/unassigned;
- число задействованных инженеров;
- общий пробег и travel time;
- компоненты `unassigned_penalty`, `used_engineers_penalty`,
  `distance_penalty`, `travel_time_penalty`, `plan_disruption_penalty` и
  `total_objective`;
- процентное сравнение OR-Tools с Baseline словами «сократил», «увеличил»,
  «назначил больше» или «назначил меньше»;
- пробег OR-Tools по каждому инженеру, включая нулевые маршруты;
- причины недопустимости контрольного плана.

Основные метрики ТЗ — `used_engineers_count` и километраж. План с меньшим
пробегом, полученный за счёт пропуска заявок, не считается лучше: это видно по
`unassigned_penalty` и числу назначенных заявок.

`total_objective` можно сравнивать только между запусками с одинаковыми
весами, routing data, составом задач и режимом статусов. Coordinate и OSRM
планы сравниваются по качеству только внутри одного routing provider.

## OSRM-кэш

Кэш включён только в `OSRMRoutingProvider`:

- SQLite хранит отдельные направленные пары;
- NPZ хранит готовую матрицу для набора координат;
- memory cache сокращает повторные запросы внутри процесса.

По умолчанию пути находятся в `.cache/osrm/`. Их можно изменить:

```bash
OSRM_PAIR_CACHE_PATH=/tmp/osrm_pairs.sqlite3 \
OSRM_MATRIX_CACHE_PATH=/tmp/osrm_matrices \
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider osrm --iterations 1
```

Уровень выключается значением `off` или `none`:

```bash
OSRM_PAIR_CACHE_PATH=off OSRM_MATRIX_CACHE_PATH=off \
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider osrm --iterations 1
```

Кэш сокращает подготовку матриц и нагрузку на внешний OSRM, но не ускоряет
сам поиск OR-Tools, Baseline или Timefold. Автоматического TTL нет: после
обновления дорожного графа кэш нужно очистить или сменить путь.

## Интерпретация сравнения

Baseline — воспроизводимая нижняя планка из ТЗ. OR-Tools может использовать
меньше инженеров и километров, потому что одновременно выбирает исполнителя и
порядок, тогда как Baseline принимает первое допустимое назначение. ICO-DE и
Timefold показываются как дополнительные исследовательские варианты; их
нельзя считать заменой OR-Tools без проверки тех же сценариев.

Контрольное распределение полезно как реальный ориентир составителей, но оно
может быть физически невыполнимым после проверки окон, дороги и смены. В этом
случае benchmark явно выводит нарушения, а не скрывает их.
