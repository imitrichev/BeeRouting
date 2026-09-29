# Тесты и бенчмарки

Бенчмарк измеряет текущую производительность и качество планов. В отличие от
модульного теста, он не устанавливает жёсткого требования «решение должно
работать быстрее N секунд». Время зависит от процессора, версии OR-Tools,
лимита поиска, доступности OSRM, состояния кэша и количества итераций.

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
java -version
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

Если Java или Python API Timefold недоступны, бенчмарк выводит причину и
пропускает только Timefold. Baseline и OR-Tools продолжают выполняться.

## Установка Timefold (Linux) для проведения полного бенчмарка всех решателей

Выполните из корня проекта:

  curl -LsSf https://astral.sh/uv/install.sh \
    -o /tmp/install-uv.sh

  sh /tmp/install-uv.sh

  export PATH="$HOME/.local/bin:$PATH"

Установите Python 3.12 внутрь .tools:

  export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python"

  uv python install 3.12
  uv python list

Создайте .timefold-venv:

  UV_PYTHON_INSTALL_DIR="$PWD/.tools/python" \
  uv venv --python 3.12 .timefold-venv

Проверьте:

  .timefold-venv/bin/python --version

Должно получиться примерно:

  Python 3.12.x

Установите зависимости:

  uv pip install \
    --python .timefold-venv/bin/python \
    pip

  uv pip install \
    --python .timefold-venv/bin/python \
    -r backend/optimization/requirements-timefold.txt

Установите JDK 21.0.2:

  mkdir -p .tools/jdk-21.0.2

  curl -fL \
    "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.2%2B13/OpenJDK21U-jdk_x64_linux_hotspot_21.0.2_13.tar.gz" -o /tmp/temurin-jdk-21.0.2.tar.gz

  tar -xzf /tmp/temurin-jdk-21.0.2.tar.gz \
    -C .tools/jdk-21.0.2 \
    --strip-components=1

Проверьте установку Java:

  .tools/jdk-21.0.2/bin/java -version

Ожидается версия 21.0.2.

Проверьте Java и Timefold:

  JAVA_HOME="$PWD/.tools/jdk-21.0.2" \
  PATH="$JAVA_HOME/bin:$PATH" \
  .timefold-venv/bin/python -c \
    "import timefold; print('Timefold установлен')"

Запуск бенчмарка:

  JAVA_HOME="$PWD/.tools/jdk-21.0.2" \
  PATH="$JAVA_HOME/bin:$PATH" \
  PYTHONPATH="$PWD" \
  .timefold-venv/bin/python -m \
    backend.optimization.benchmarks.benchmark_yugo_center \
    --include-ico-de --include-timefold \
    --routing-provider coordinate --iterations 1

## Автоматические проверки

Полный набор проверок состоит из тестов математического ядра, тестов Django
API и production-сборки клиентского приложения:

```bash
.venv/bin/python -m pytest backend/optimization/tests -q
.venv/bin/python backend/web_mvp/manage.py test \
  backend.web_mvp.api_v2.tests backend.web_mvp.api_v2.tests_planning -v 1
cd client
npm run build
```

Тесты ядра и API используют детерминированные матрицы и подменённые сетевые
ответы, поэтому для их запуска не нужны реальные OSRM, OTP и Nominatim.
Интеграция с настоящими дорожными данными проверяется отдельно бенчмарком с
параметром `--routing-provider osrm`.

## Малый бенчмарк OR-Tools

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

## Крупный детерминированный бенчмарк

Файл: `backend/optimization/benchmarks/benchmark_ortools_large.py`.

Содержит 15 инженеров и 100 заявок. Матрицы строятся в памяти; бенчмарк
нужен для наблюдения за ростом времени на более крупной задаче.

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_ortools_large \
  --iterations 1
```

## Сравнительные бенчмарки трёх районов

Точки входа и используемые по умолчанию наборы данных:

| Район | Модуль | JSON |
|---|---|---|
| Югоцентр | `benchmark_yugo_center` | `Югоцентр.json` |
| Восток | `benchmark_vostok` | `Восток.json` |
| Юго-восток | `benchmark_yugo_vostok` | `Юго-восток.json` |

Все три точки входа используют общую реализацию сравнительного бенчмарка,
поэтому поддерживают одинаковые решатели, параметры и формат результата.
Общая реализация находится в
`backend/optimization/benchmarks/benchmark_region.py`. Её можно запустить для
любого совместимого района, явно передав JSON:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_region \
  --path "Югоцентр.json" \
  --routing-provider coordinate --iterations 1
```

Скрипт загружает актуальный `Югоцентр.json`, строит маршрутные данные и
сопоставляет результаты:

1. контрольное распределение составителей из полей `reference_*` в JSON;
2. `GreedyBaselineOptimizer`;
3. `ORToolsOptimizer`;
4. `ICOOptimizer`, если указан `--include-ico-de`;
5. `TimefoldOptimizer`, если указан `--include-timefold` и доступна JVM.

Контрольное распределение не является результатом работы решателя. JSON хранит
для каждой заявки `reference_crew` и `reference_status`. Эти данные задают пары
«заявка — инженер», но не порядок посещения, поэтому бенчмарк загружает их для
сопоставления и не выдаёт за готовый маршрут. Временные и маршрутные hard
constraints проверяются только у планов, действительно построенных решателями.
Для контрольного распределения маршрутные метрики в таблице отмечаются
прочерками: без порядка посещения их нельзя рассчитать корректно.

Запуск всех трёх районов на воспроизводимой coordinate-матрице без сети:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider coordinate --iterations 1
.venv/bin/python -m backend.optimization.benchmarks.benchmark_vostok \
  --routing-provider coordinate --iterations 1
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_vostok \
  --routing-provider coordinate --iterations 1
```

### Источник контрольного плана

Файлы `* Контрольное распределение.csv` остаются входными данными генератора
набора и используются в тестах импорта. Сам бенчмарк не читает CSV. Генератор
переносит из него исполнителя и статус в JSON; порядок строк не трактуется как
последовательность маршрута.

Исторические версии сохранены как `*_old.csv` и `*_old.json`; при работе
приложения они не используются. Актуальные JSON собраны из исправленных CSV с
исходными именами.

Исторические JSON следует проверять через общую точку входа. Флаг
`--ignore-task-statuses` снимает фиксацию старых рабочих статусов и позволяет
решателям заново планировать все заявки, включая `COMPLETED` и `CANCELLED`:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_region \
  --path "Югоцентр_old.json" --routing-provider coordinate \
  --iterations 1 --ignore-task-statuses
.venv/bin/python -m backend.optimization.benchmarks.benchmark_region \
  --path "Восток_old.json" --routing-provider coordinate \
  --iterations 1 --ignore-task-statuses
.venv/bin/python -m backend.optimization.benchmarks.benchmark_region \
  --path "Юго-восток_old.json" --routing-provider coordinate \
  --iterations 1 --ignore-task-statuses
```

Без `--ignore-task-statuses` исторический Юго-восток останавливается на
проверке status-aware контракта: в исходных данных одна начатая заявка
закреплена за исполнителем, которому Baseline не может её назначить. Для
анализа исторического контрольного распределения это ещё одна причина
использовать приведённые выше команды полного утреннего расчёта.

Полное сравнение с двумя дополнительными решателями:

```bash
JAVA_HOME="$PWD/.tools/jdk-21.0.2" \
PATH="$JAVA_HOME/bin:$PATH" \
PYTHONPATH="$PWD" \
.timefold-venv/bin/python -m \
  backend.optimization.benchmarks.benchmark_yugo_center \
  --include-ico-de --include-timefold \
  --routing-provider coordinate --iterations 1
```

Бенчмарк всегда запускает Baseline и OR-Tools. ICO-DE и Timefold отключены
по умолчанию, чтобы обычный запуск оставался коротким.

## Coordinate- и OSRM-матрицы

`--routing-provider coordinate` использует haversine-расстояние между
координатами и демонстрационную скорость. Это расстояние по прямой, а не
дорожный маршрут. Результат воспроизводим и не зависит от сети.

`--routing-provider osrm` использует OSRM Table для времени и расстояния и
OSRM Route для геометрии. Профиль выбирается по типу транспорта инженера.
`PUBLIC_TRANSPORT` остаётся приближением: приложение использует автомобильный
граф и удваивает время, потому что обычный OSRM не моделирует расписание и
пересадки общественного транспорта.

Все три актуальных района на дорожных матрицах запускаются так:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider osrm --iterations 1 --osrm-timeout-seconds 30
.venv/bin/python -m backend.optimization.benchmarks.benchmark_vostok \
  --routing-provider osrm --iterations 1 --osrm-timeout-seconds 30
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_vostok \
  --routing-provider osrm --iterations 1 --osrm-timeout-seconds 30
```

Чтобы воспроизвести режим, который текущий frontend использует по умолчанию,
добавьте полный пересчёт и учёт оборудования:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider osrm --iterations 1 --osrm-timeout-seconds 30 \
  --ignore-task-statuses --consider-equipment
```

Параметр OSRM относится к тому же бенчмарку: отдельного сценария для OSRM нет.
Время импорта и построения матриц выводится отдельно от времени работы
решателя. Районные CLI-бенчмарки напрямую строят статические OSRM-матрицы;
итерационное уточнение общественного транспорта через OTP выполняется только
сервисом планирования Django API и в эти замеры не входит.

## Актуальные результаты

Результаты ниже получены 29 сентября 2026 года: одна измеряемая итерация после
прогрева, режим учёта статусов, перенос `ASSIGNED` разрешён, учёт роутеров
выключен. Время построения сетевых матриц зависит от кэша и состояния внешних
сервисов, поэтому в таблицах приведено только время работы решателей.

### Coordinate-матрица

| Район и план | Назначено | Инженеров | Пробег, км | Время в пути, мин | Время расчёта, с |
|---|---:|---:|---:|---:|---:|
| Югоцентр, контрольный | 14 | 4 | 35,019 | 111 | 0,000397 |
| Югоцентр, Baseline | 14 | 7 | 52,843 | 210 | 0,000580 |
| Югоцентр, OR-Tools | 14 | 4 | 34,748 | 106 | 0,031644 |
| Восток, контрольный | 22 | 7 | 62,049 | 136 | 0,000268 |
| Восток, Baseline | 24 | 10 | 102,529 | 290 | 0,001450 |
| Восток, OR-Tools | 24 | 7 | 58,781 | 128 | 0,094871 |
| Юго-восток, контрольный | 34 | 10 | 142,946 | 331 | 0,000368 |
| Юго-восток, Baseline | 32 | 10 | 564,055 | 1 225 | 0,002831 |
| Юго-восток, OR-Tools | 34 | 8 | 193,390 | 429 | 0,153930 |

Все три актуальных контрольных плана соблюдают жёсткие ограничения на
coordinate-матрице. OR-Tools назначил все доступные для текущего расчёта
заявки и использовал не больше инженеров, чем контрольный план.

### OSRM-матрица

| Район и план | Назначено | Инженеров | Пробег, км | Время в пути, мин | Время расчёта, с |
|---|---:|---:|---:|---:|---:|
| Югоцентр, контрольный | 14 | 4 | 53,102 | 159 | 0,000190 |
| Югоцентр, Baseline | 14 | 7 | 77,726 | 269 | 0,000799 |
| Югоцентр, OR-Tools | 14 | 4 | 50,132 | 131 | 0,027605 |
| Восток, контрольный | 22 | 7 | 104,227 | 173 | 0,000287 |
| Восток, Baseline | 24 | 10 | 143,346 | 338 | 0,001739 |
| Восток, OR-Tools | 24 | 7 | 94,681 | 165 | 0,075819 |
| Юго-восток, контрольный | 34 | 10 | 212,392 | 344 | 0,000381 |
| Юго-восток, Baseline | 34 | 10 | 856,272 | 937 | 0,002066 |
| Юго-восток, OR-Tools | 34 | 8 | 185,624 | 328 | 0,160102 |

Все актуальные контрольные планы допустимы и на OSRM-матрицах. OR-Tools во
всех трёх районах назначил не меньше заявок, использовал не больше инженеров и
сократил пробег относительно Baseline.

### Исторические контрольные распределения

Исторические планы проверены на coordinate-матрице в полном утреннем режиме.
Их метрики не приводятся, поскольку каждый план нарушает жёсткие ограничения:

| JSON | Заявок в расчёте | Нарушений | Временное окно | Выход за смену | OR-Tools: назначено | OR-Tools: инженеров | OR-Tools: пробег, км |
|---|---:|---:|---:|---:|---:|---:|---:|
| `Югоцентр_old.json` | 56 | 64 | 34 | 30 | 56 | 7 | 99,080 |
| `Восток_old.json` | 66 | 72 | 44 | 28 | 66 | 9 | 133,151 |
| `Юго-восток_old.json` | 83 | 83 | 51 | 32 | 81 | 11 | 283,891 |

### Полный режим frontend

На актуальном `Югоцентр.json` с OSRM, `--ignore-task-statuses` и
`--consider-equipment` получены результаты, соответствующие сценарию
демонстрации из главного README:

| План | Назначено | Неназначено | Инженеров | Пробег, км | Время в пути, мин | Время расчёта, с |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 45 | 11 | 11 | 325,146 | 870 | 0,005226 |
| OR-Tools | 56 | 0 | 10 | 155,378 | 602 | 0,503398 |

### Малый и крупный сценарии

Оба самостоятельных бенчмарка используют ручные детерминированные матрицы.
При одной измеряемой итерации после прогрева получены следующие результаты:

| Сценарий | Размер | Время OR-Tools, с |
|---|---|---:|
| Малый | 3 инженера, 5 заявок | 0,003652 |
| Крупный | 15 инженеров, 100 заявок | 2,911153 |

## Статусы заявок

По умолчанию бенчмарк учитывает текущие статусы заявок:

- `CANCELLED` и `COMPLETED` исключаются из нового плана;
- `EN_ROUTE` и `IN_PROGRESS` фиксируются за `current_engineer_id`;
- `ASSIGNED` можно переносить;
- `NOT_SENT` и `OVERDUE` планируются;
- `--preserve-assigned` дополнительно запрещает перенос `ASSIGNED`.

Полный новый план с игнорированием рабочих статусов запускается так:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider coordinate --iterations 1 \
  --ignore-task-statuses
```

Это отдельный режим утреннего перераспределения и сравнения решателей. В нём
статусы источника не фиксируют назначения, а в расчёт входят все заявки,
включая отменённые и выполненные.

Учёт количества роутеров включается отдельно:

```bash
.venv/bin/python -m backend.optimization.benchmarks.benchmark_yugo_center \
  --routing-provider coordinate --iterations 1 --consider-equipment
```

## Параметры сравнительных бенчмарков

| Параметр | По умолчанию | Назначение |
|---|---:|---|
| `--path` | JSON выбранного района | JSON-сценарий |
| `--routing-provider` | `coordinate` | `coordinate` или `osrm` |
| `--iterations` | `3` | Число измерений каждого решателя |
| `--time-limit-minutes` | `1` | Лимит OR-Tools и ICO-DE |
| `--timefold-time-limit-seconds` | `20` | Лимит поиска Timefold |
| `--osrm-timeout-seconds` | `30` | Тайм-аут HTTP-запроса OSRM |
| `--preserve-assigned` | выключен | Фиксировать `ASSIGNED` |
| `--ignore-task-statuses` | выключен | Перестроить план по всем заявкам |
| `--consider-equipment` | выключен | Учитывать запас роутеров |
| `--include-ico-de` | выключен | Добавить ICO-DE |
| `--include-timefold` | выключен | Добавить Timefold при доступной JVM |

`--iterations 1` означает один измеряемый запуск каждого включённого решателя,
а не «решить только одну заявку». Перед измерениями Baseline и OR-Tools всё
равно выполняется прогревочный запуск. Время Timefold включает холодный запуск
JVM, поэтому его нельзя напрямую сравнивать с чистым временем решателя Python.

## Что выводит бенчмарк

В консоли отображаются:

- источник JSON и поставщик маршрутных данных;
- количество инженеров и заявок;
- распределение статусов и состав входа в новый план;
- время импорта и построения матриц;
- время работы каждого решателя;
- assigned/unassigned;
- число задействованных инженеров;
- общий пробег и время в пути;
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
весами, маршрутными данными, составом задач и режимом статусов. Планы,
полученные через Coordinate и OSRM, сравниваются по качеству только внутри
одного поставщика маршрутных данных.

## OSRM-кэш

Кэш включён только в `OSRMRoutingProvider`:

- SQLite хранит отдельные направленные пары;
- NPZ хранит готовую матрицу для набора координат;
- кэш в памяти сокращает количество повторных запросов внутри процесса.

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
случае бенчмарк явно выводит нарушения, а не скрывает их.
