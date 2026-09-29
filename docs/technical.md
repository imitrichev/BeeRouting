# Дополнительные технические сведения о BeeRouting

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

### Переменные окружения OSRM

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
транспорта: автомобильный OSRM с удвоенным временем. После построения плана
OpenTripPlanner запрашивается только для фактических дуг инженеров
`PUBLIC_TRANSPORT`. Успешно полученные значения времени и расстояния заменяют
fallback, после чего OR-Tools запускается повторно, используя предыдущий план
как начальное решение. По умолчанию выполняется не более двух уточняющих
итераций.

Пустой `tripPatterns`, в том числе для точек за пределами московского GTFS,
сохраняется в кэше как `no_route`, и для пары остаётся расчёт `car × 2`.
Сетевая, HTTP- или GraphQL-ошибка также включает fallback и отключает
новые запросы к OTP до конца текущего расчёта.

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `OTP_ENABLED` | Включить точечное уточнение через OTP | `true` |
| `OTP_URL` | Адрес GraphQL API OTP Transmodel | `http://127.0.0.1:8081/otp/transmodel/v3` |
| `OTP_SERVICE_DATE` | Дата поездки, доступная в GTFS | `2026-08-17` |
| `OTP_TIMEZONE` | Часовой пояс запросов | `Europe/Moscow` |
| `OTP_TIME_BUCKET_MINUTES` | Размер временного интервала кэша | `30` |
| `OTP_TIMEOUT_SECONDS` | Тайм-аут одного запроса | `4` |
| `OTP_MAX_REFINEMENT_ITERATIONS` | Максимум повторных уточнений и запусков OR-Tools | `2` |
| `OTP_REFINEMENT_SOLVER_TIME_LIMIT_SECONDS` | Лимит одного уточняющего запуска OR-Tools | `10` |
| `OTP_CACHE_PATH` | SQLite-кэш успешных и пустых маршрутов | `.cache/otp/otp_routes.sqlite3` |

Ключ OTP-кэша включает координаты начала и конца, дату, округлённое время
отправления и адрес сервиса. Значение `off` в `OTP_CACHE_PATH` отключает файловый
кэш. `OTP_ENABLED=false` полностью отключает уточнение и сохраняет прежнее
поведение `car × 2`.

`OSRM_BASE_URL` задаёт один общий адрес сразу для всех типов транспорта. Его
следует использовать только с собственным сервером, на котором действительно
настроены профили `driving`, `walking` и `cycling`. Переменные для отдельных
типов транспорта имеют приоритет над `OSRM_BASE_URL`.

Пример запуска серверной части с явным указанием публичных сервисов:

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

## Другое

По умолчанию Django использует локальную базу SQLite в файле
`backend/web_mvp.sqlite3`. Дополнительная настройка базы не требуется.

Команды тестирования, настройка Timefold и сравнение решателей собраны в
[документе о тестах и бенчмарках](benchmarks.md). Математическая модель
описана в [документации по оптимизации](optimization.md).
