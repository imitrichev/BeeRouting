# Разное (документация BeeRouting)

## Маршрутизация

Для обычного запуска устанавливать OSRM не требуется. Если переменные
окружения не заданы, BeeRouting использует следующие публичные сервисы:

| Транспорт | Адрес |
|---|---|
| Автомобиль | `https://router.project-osrm.org` |
| Пешком | `https://routing.openstreetmap.de/routed-foot` |
| Велосипед | `https://routing.openstreetmap.de/routed-bike` |
| Общественный транспорт | автомобильный OSRM; время умножается на `2` |

Проверить доступность автомобильного сервиса можно командой:

```bash
curl -fsS \
  'https://router.project-osrm.org/route/v1/driving/37.61,55.75;37.62,55.76?overview=false'
```

После успешного запроса в ответе будет JSON с полем `"code":"Ok"`.

#### Переменные окружения OSRM

Перед запуском Django можно переопределить адрес и профиль для каждого типа
транспорта:

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `OSRM_CAR_BASE_URL` | Автомобильный сервер | `https://router.project-osrm.org` |
| `OSRM_WALK_BASE_URL` | Пеший сервер | `https://routing.openstreetmap.de/routed-foot` |
| `OSRM_BICYCLE_BASE_URL` | Велосипедный сервер | `https://routing.openstreetmap.de/routed-bike` |
| `OSRM_PUBLIC_TRANSPORT_BASE_URL` | Основа расчёта общественного транспорта | `https://router.project-osrm.org` |
| `OSRM_CAR_PROFILE` | Имя автомобильного профиля в URL | `driving` |
| `OSRM_WALK_PROFILE` | Имя пешего профиля в URL | `driving` для публичного сервера |
| `OSRM_BICYCLE_PROFILE` | Имя велосипедного профиля в URL | `driving` для публичного сервера |
| `OSRM_PUBLIC_TRANSPORT_PROFILE` | Профиль основы общественного транспорта | `driving` |
| `OSRM_TIMEOUT_SECONDS` | Тайм-аут HTTP-запроса | `15` |
| `OSRM_MAX_RATE_LIMIT_RETRIES` | Повторы после HTTP 429 | `2` |
| `OSRM_RATE_LIMIT_BACKOFF_SECONDS` | Начальная пауза между повторами | `2` |
| `OSRM_PAIR_CACHE_PATH` | SQLite-кэш отдельных пар | `.cache/osrm/osrm_pairs.sqlite3` |
| `OSRM_MATRIX_CACHE_PATH` | Каталог NPZ-кэша матриц | `.cache/osrm/matrices` |

### Уточнение общественного транспорта через OTP

Первый запуск OR-Tools использует полную fallback-матрицу общественного
транспорта: автомобильный OSRM и удвоенное время. После построения плана
OpenTripPlanner запрашивается только для фактических дуг инженеров
`PUBLIC_TRANSPORT`. Успешные значения времени и расстояния заменяют fallback,
после чего OR-Tools повторно запускается с предыдущим планом как initial
solution. По умолчанию допускается не более двух уточняющих итераций.

Пустой `tripPatterns`, в том числе для точек за пределами московского GTFS,
сохраняется в кэше как `no_route`, и для пары остаётся `car × 2`. Сетевая,
HTTP- или GraphQL-ошибка также включает fallback и отключает новые OTP-запросы
до конца текущего расчёта.

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `OTP_ENABLED` | Включить точечное уточнение через OTP | `true` |
| `OTP_URL` | GraphQL endpoint OTP Transmodel API | `http://127.0.0.1:8081/otp/transmodel/v3` |
| `OTP_SERVICE_DATE` | Дата поездки, доступная в GTFS | `2026-08-17` |
| `OTP_TIMEZONE` | Часовой пояс запросов | `Europe/Moscow` |
| `OTP_TIME_BUCKET_MINUTES` | Размер временного bucket кэша | `30` |
| `OTP_TIMEOUT_SECONDS` | Тайм-аут одного запроса | `4` |
| `OTP_MAX_REFINEMENT_ITERATIONS` | Максимум повторных уточнений и запусков OR-Tools | `2` |
| `OTP_REFINEMENT_SOLVER_TIME_LIMIT_SECONDS` | Лимит одного уточняющего запуска OR-Tools | `10` |
| `OTP_CACHE_PATH` | SQLite-кэш успешных и пустых маршрутов | `.cache/otp/otp_routes.sqlite3` |

Ключ OTP-кэша включает координаты начала и конца, дату, округлённое время
отправления и endpoint. Значение `off` в `OTP_CACHE_PATH` отключает файловый
кэш. `OTP_ENABLED=false` полностью отключает уточнение и сохраняет прежнее
поведение `car × 2`.

`OSRM_BASE_URL` задаёт один общий адрес сразу для всех типов транспорта. Его
следует использовать только с собственным сервером, на котором действительно
настроены профили `driving`, `walking` и `cycling`. Переменные для отдельных
типов транспорта имеют приоритет над `OSRM_BASE_URL`.

Пример запуска backend с явным указанием публичных сервисов:

```bash
OSRM_CAR_BASE_URL=https://router.project-osrm.org \
OSRM_WALK_BASE_URL=https://routing.openstreetmap.de/routed-foot \
OSRM_BICYCLE_BASE_URL=https://routing.openstreetmap.de/routed-bike \
OSRM_PUBLIC_TRANSPORT_BASE_URL=https://router.project-osrm.org \
OSRM_TIMEOUT_SECONDS=30 \
  .venv/bin/python backend/web_mvp/manage.py runserver 8000
```

Чтобы отключить файловый кэш для одного запуска, передайте:

```bash
OSRM_PAIR_CACHE_PATH=off \
OSRM_MATRIX_CACHE_PATH=off \
  .venv/bin/python backend/web_mvp/manage.py runserver 8000
```

## Решатель Timefold

Timefold используется только в сравнительных benchmark и не нужен для работы
веб-приложения. Он требует Python 3.10–3.12 и JDK 17 или новее, поэтому для
него создаётся отдельное окружение:

```bash
python3.12 -m venv .timefold-venv
.timefold-venv/bin/python -m pip install \
  -r backend/optimization/requirements-timefold.txt
java -version
```

Пример запуска сравнения:

```bash
PYTHONPATH="$PWD" .timefold-venv/bin/python \
  -m backend.optimization.benchmarks.benchmark_yugo_center \
  --include-timefold \
  --routing-provider coordinate \
  --iterations 1
```

## Benchmark и решатели

Основные сравнительные сценарии находятся в `backend/optimization/benchmarks/`:
`benchmark_yugo_center.py`, `benchmark_vostok.py` и
`benchmark_yugo_vostok.py`. Они сравнивают
контрольный план составителей, Baseline и OR-Tools; ICO-DE и Timefold
подключаются отдельно. Benchmark выводит время, назначенные заявки,
неназначенные заявки, задействованных инженеров, расстояние, travel time,
декомпозицию objective, процентное сравнение OR-Tools с Baseline и пробег по
каждому инженеру.

Все три entry point вызывают общий `benchmark_region.py`. Его можно применять
к другому району, передав `--path`; контрольный план читается из reference-полей
этого же JSON.

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider coordinate --iterations 1
```

Для двух других районов используются те же параметры:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_vostok \
  --routing-provider coordinate --iterations 1
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_vostok \
  --routing-provider coordinate --iterations 1
```

CSV контрольного распределения используется только генератором JSON и его
тестами. Runtime benchmark к CSV не обращается. Подробнее это описано в
[документации benchmark](benchmarks.md).

Для реальных дорог:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider osrm --iterations 1 --osrm-timeout-seconds 30
```

Все четыре варианта:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --include-ico-de --include-timefold \
  --routing-provider osrm --iterations 1
```

`--ignore-task-statuses` строит полный новый утренний план, игнорируя
operational-статусы, но никогда не возвращает в работу отменённые заявки:
`CANCELLED` исключаются во всех режимах. Без этого флага дополнительно
исключаются `COMPLETED`, заявки `EN_ROUTE` и `IN_PROGRESS` фиксируются, а
`ASSIGNED` можно переносить. `--preserve-assigned` дополнительно фиксирует и
`ASSIGNED`. `--consider-equipment` включает количественный учёт роутеров. OSRM
использует SQLite-кэш пар и NPZ-кэш матриц; coordinate provider
кэш не использует.

Подробные команды, параметры и интерпретация результатов собраны в
[benchmarks.md](benchmarks.md).

Кратко о решателях:

- **Baseline** — заявки идут по входному порядку, инженеры проверяются по
  входному порядку, глобального поиска нет. Это эталон из ТЗ.
- **OR-Tools** — основной solver VRPTW: одновременно выбирает инженера,
  порядок, расписание и допустимые пропуски; оптимизирует число инженеров,
  пробег и travel time с настроенными штрафами.
- **ICO-DE** — экспериментальная метаэвристика с random keys. Используется
  для сравнения и исследований, но не заменяет OR-Tools.
- **Timefold** — дополнительный solver с planning list variable и constraint
  streams. Нужны отдельное Python-окружение и JDK 17+; отсутствие Java не
  мешает запуску Baseline и OR-Tools.

Подробное объяснение OR-Tools, ограничений, матриц и результата — в
[optimization.md](optimization.md).

## Тесты

```bash
.venv/bin/python -m pytest backend/optimization/tests -q
.venv/bin/python backend/web_mvp/manage.py test \
  backend.web_mvp.api_v2.tests backend.web_mvp.api_v2.tests_planning -v 1
```

Клиентское приложение проверяется сборкой:

```bash
cd client
npm run build
```

Тесты используют детерминированные матрицы и не требуют OSRM. OSRM benchmark
проверяет интеграцию с реальным routing provider отдельно.

## Другое
По умолчанию Django использует локальную базу SQLite в файле
`backend/web_mvp.sqlite3`. Дополнительная настройка базы не требуется.
