# BeeRouting web MVP

Web-слой состоит из Django/DRF API v2 и Vue 3 + TypeScript + Vite + Vuetify
frontend с MapLibre. Optimization Engine остаётся независимым от Django.

## Запуск

Из корня проекта:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python backend/web_mvp/manage.py migrate
.venv/bin/python backend/web_mvp/manage.py runserver 8000
```

В отдельном терминале:

```bash
cd frontend
npm install
npm run dev
```

Откройте <http://127.0.0.1:5173>.

Для production-сборки frontend:

```bash
npm run build
```

Текущий `runserver` предназначен для локальной демонстрации. Для сервера
нужно отдавать `frontend/dist` через web-сервер, а Django запускать через
WSGI/ASGI-сервер.

## Сценарий интерфейса

1. `Перезагрузить официальный датасет` заново импортирует Восток,
   Юго-восток и Югоцентр и очищает сохранённые планы.
2. Выпадающий список переключает район без нового расчёта.
3. `Baseline (жадный алгоритм)` показывает эталон из ТЗ.
4. `Распределить заявки (OR-Tools)` запускает основной solver.
5. Флажок `Учитывать оборудование` включает расход роутеров.
6. `Статусы заявок из контрольного распределения` копирует только статусы из
   контрольных данных и не меняет текущих инженеров рабочего плана.
7. `Сценарии перепланирования...` открывает аварийную заявку, отмену заявки и
   недоступность инженера.
8. Создание и ручное переназначение проходят через API-сервис с проверкой
   адреса, навыка, транспорта, оборудования, окна и смены.
9. Кнопка-облачко у заявки показывает объяснение. В developer-режиме виден
   исходный JSON двухступенчатой проверки, в production-режиме — только
   человекочитаемый текст.

## API

Все маршруты находятся под `/api/v2/`. Устаревшего `/api/v1/` в текущем
проекте нет. Полный список endpoint’ов — в [`docs/api-v2.md`](../../docs/api-v2.md).

По умолчанию API использует OSRM: Table service для матриц и Route service для
линий маршрутов. Переменные окружения:

```bash
OSRM_BASE_URL=http://localhost:5000 \
OSRM_TIMEOUT_SECONDS=15 \
.venv/bin/python backend/web_mvp/manage.py runserver 8000
```

Для разных типов транспорта поддерживаются отдельные `OSRM_*_BASE_URL` и
профили. Публичный OSRM обычно не знает расписание общественного транспорта;
`PUBLIC_TRANSPORT` поэтому использует автомобильный граф и коэффициент времени
2.0. Пеший и велосипедный режимы требуют подходящих профилей/endpoint’ов.

Без сети тесты используют детерминированный `CoordinateRoutingProvider`.

## Режимы статусов

API по умолчанию учитывает текущие статусы. `CANCELLED` и `COMPLETED` не
планируются, `EN_ROUTE` и `IN_PROGRESS` фиксируются, `ASSIGNED` можно
переносить, `NOT_SENT` и `OVERDUE` можно назначать. Для полного нового плана
frontend передаёт `ignore_task_statuses=true`.

Сложная логика находится в `api_v2/services`, а views/serializers только
валидируют запрос и вызывают сервис. Сохранение результата синхронизирует ORM
и domain-снимок района.

## Developer и production

```bash
# JSON-проверки доступны в окне объяснения.
BEEROUTING_MODE=developer .venv/bin/python backend/web_mvp/manage.py runserver 8000

# Технический JSON не передаётся frontend.
BEEROUTING_MODE=production .venv/bin/python backend/web_mvp/manage.py runserver 8000
```

LLM получает только структурированные факты от Optimization Engine и не
принимает решений о назначении.
