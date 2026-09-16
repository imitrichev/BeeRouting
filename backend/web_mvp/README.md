# BeeRouting web MVP

Минимальный end-to-end сценарий состоит из независимого Optimization Engine,
Django/DRF API и Vue 3 интерфейса.

## Запуск

В первом терминале из корня проекта:

```bash
.venv/bin/pip install -r backend/web_mvp/requirements.txt
.venv/bin/python backend/web_mvp/manage.py runserver 8000
```

Во втором терминале:

```bash
cd frontend
npm install
npm run dev
```

Откройте <http://localhost:5173>.

## API

- `GET /api/dataset/official/` — открыть `yugo_center.json`;
- `POST /api/dataset/upload/` — загрузить JSON в поле `file`;
- `POST /api/optimize/` — запустить OR-Tools для текущего dataset.

По умолчанию API использует `OSRMRoutingProvider`. Он запрашивает у OSRM
матрицу времени и расстояний через [Table service](https://project-osrm.org/docs/v5.22.0/api/#table-service),
а после оптимизации — дорожную GeoJSON-геометрию каждого маршрута через
[Route service](https://project-osrm.org/docs/v5.22.0/api/#route-service).
Адрес сервера можно изменить переменной окружения:

```bash
OSRM_BASE_URL=http://localhost:5000 OSRM_TIMEOUT_SECONDS=15 \
  .venv/bin/python backend/web_mvp/manage.py runserver 8000
```

Профили OSRM выбираются по типу транспорта: `driving` для автомобиля,
`walking` для пешего маршрута и `cycling` для велосипеда. Стандартный OSRM не
моделирует расписания и пересадки общественного транспорта, поэтому
`PUBLIC_TRANSPORT` явно использует профиль `driving` как приближение. При
собственном сервере с подходящим профилем его можно передать в
`OSRMRoutingProvider.profiles`.

Для полностью воспроизводимых тестов и работы без сети API-тесты переключают
`use_osrm = False`; в этом режиме используется детерминированный
`CoordinateRoutingProvider`.
