# Техническая документация BeeRouting

## Фичи проекта

- загрузка трёх официальных районов и пользовательских JSON;
- отдельное хранение плана каждого района, поэтому переключение района не
  требует повторной оптимизации;
- Baseline — заданный ТЗ жадный алгоритм;
- основной `ORToolsOptimizer` на Google OR-Tools;
- экспериментальный `ICOOptimizer` на ICO-DE/random keys и дополнительный
  `TimefoldOptimizer` для сравнения;
- временные окна и рабочие смены как жёсткие ограничения;
- квалификация и тип транспорта как жёсткие ограничения;
- опциональный учёт количества роутеров у инженера;
- расчёт времени движения и расстояния отдельно для каждого типа транспорта;
- OSRM-матрицы и дорожная геометрия маршрута для MapLibre;
- три события перепланирования: срочная заявка, отмена заявки и
  недоступность инженера;
- ручное переназначение с предварительной проверкой, причинами отказа и
  подтверждением изменения метрик;
- создание заявки через интерфейс с геокодированием адреса и нормативной
  длительностью;
- статусы заявок, фиксация уже начатых работ и сохранение плана в БД;
- сохраняемый признак доступности инженера `Engineer.is_active`: недоступный
  инженер исключается из текущего и всех последующих расчётов;
- аварийные заявки всегда получают приоритет `URGENT`, в том числе при импорте
  старого JSON с ошибочно указанным обычным приоритетом;
- двухступенчатые структурированные объяснения решения и необязательная
  генерация текста через LLM.

Решение принимает только Optimization Engine. LLM получает факты проверки и
не участвует в назначении заявки.

## Соответствие ТЗ

| Требование 13.pdf | Реализация |
|---|---|
| Распределить заявки и определить порядок визитов | OR-Tools, Baseline, ICO-DE, Timefold |
| Навык заявки входит в навыки инженера | Hard constraint; используются `LOCAL_WORKS`, `CONNECTION_AND_UPSELL`, `EMERGENCY_WORKS` |
| Работа укладывается в смену | Hard constraint с учётом дороги, ожидания и длительности работы |
| Начало работы попадает в окно | Hard constraint; ранний приезд допускает ожидание |
| Тип транспорта | Один из `CAR`, `WALK`, `BICYCLE`, `PUBLIC_TRANSPORT`; матрицы выбираются по инженеру |
| Оборудование | Дополнительный hard constraint; для роутеров учитывается количество, режим можно выключить |
| Обязательные метрики | Число задействованных инженеров и пробег по каждому инженеру и суммарно |
| Показать маршрут на карте | MapLibre, OSRM geometry; старт маршрута — стартовая точка инженера |
| Неназначенные заявки | `unassigned_task_ids` и структурированная причина по каждой заявке |
| Перепланирование | События аварии, отмены и недоступности инженера |
| Объяснение решения | Детерминированные проверки, counterfactual-проверка и необязательный LLM-текст |

Возврат на стартовую точку после последней заявки не требуется, как указано в
ТЗ. Промышленная FSM, авторизация, мобильное приложение, Kafka и
отказоустойчивый production-контур в прототип не входят.

## Основные документы

- [Архитектура](architecture.md) — краткая схема «интерфейс → API → алгоритм →
  данные» и границы компонентов;
- [Оптимизация](optimization.md) — логика решателей, метрики, hard constraints
  и soft constraints;
- [Тестовые данные](data.md) — происхождение файлов, поля, справочники, единицы
  измерения и принятые допущения.

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

## Необязательный Timefold

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

## API v2

API доступен под `/api/v2/`; старого API v1 в проекте нет. Подробный контракт
описан в [api-v2.md](api-v2.md).

| Метод | URL | Назначение |
|---|---|---|
| `GET` | `/api/v2/territories/` | Список загруженных районов |
| `GET` | `/api/v2/dataset/?territory=...` | Текущий dataset и сохранённый план |
| `POST` | `/api/v2/dataset/official/` | Перезагрузка трёх официальных районов |
| `POST` | `/api/v2/dataset/upload/` | Загрузка JSON в поле `file` |
| `POST` | `/api/v2/optimize/` | Baseline или OR-Tools |
| `PATCH` | `/api/v2/jobs/status/` | Изменить operational-статус без перепланирования |
| `POST` | `/api/v2/sync-reference-statuses/` | Полная загрузка контрольного плана из JSON |
| `POST` | `/api/v2/tasks/` | Создание заявки с нормативной длительностью |
| `POST` | `/api/v2/geocode/` | Проверка адреса и координат |
| `POST` | `/api/v2/replan/` | Три события перепланирования |
| `POST` | `/api/v2/manual-reassignment/preview/` | Проверка ручного переноса |
| `POST` | `/api/v2/manual-reassignment/confirm/` | Подтверждение переноса |
| `POST` | `/api/v2/explain/<task_id>/` | Объяснение результата |

Детальные CRUD-маршруты инженеров, заявок, справочников и событий также
зарегистрированы через API v2. Сложная логика находится в сервисах, а не во
views и serializers; математическое ядро от Django не зависит.

После `POST /api/v2/tasks/` новая заявка немедленно появляется в
`result.unassigned` с кодом `not_distribution_attempted` и пояснением
«С момента создания этой заявки не было попыток её распределения». Эта
служебная причина не считается запуском solver и не блокирует кнопки Baseline
и OR-Tools.

Приоритет аварийной заявки всегда нормализуется до `URGENT`. Правило действует
для официальных наборов, пользовательских JSON и заявок, созданных через API,
даже если во входных данных ошибочно передан обычный приоритет.

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

Frontend проверяется сборкой:

```bash
cd frontend
npm run build
```

Тесты используют детерминированные матрицы и не требуют OSRM. OSRM benchmark
проверяет интеграцию с реальным routing provider отдельно.

## Другое
По умолчанию Django использует локальную базу SQLite в файле
`backend/web_mvp.sqlite3`. Дополнительная настройка базы не требуется.
