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

Матрицы запрашиваются с учётом транспорта инженера. Для автомобиля по
умолчанию используется `router.project-osrm.org`, для пешего режима —
`routing.openstreetmap.de/routed-foot`, для велосипеда —
`routing.openstreetmap.de/routed-bike`. У этих двух endpoints путь API всё
равно содержит профиль `driving`, но графы дорог на серверах разные. Это важно:
один только параметр `/v1/walking` на автомобильном публичном OSRM не делает
маршрут пешим.

Стандартный OSRM не моделирует расписания и пересадки общественного
транспорта, поэтому `PUBLIC_TRANSPORT` использует автомобильный граф, а время
умножается на 2.0. Это явное приближение. Для собственного многопрофильного
сервера задайте `OSRM_BASE_URL`; тогда приложение будет использовать его
профили `driving`, `walking` и `cycling`. При необходимости endpoints и имена
профилей можно переопределить переменными `OSRM_WALK_BASE_URL`,
`OSRM_BICYCLE_BASE_URL`, `OSRM_CAR_BASE_URL`, `OSRM_WALK_PROFILE`,
`OSRM_BICYCLE_PROFILE` и аналогичными переменными для остальных режимов.

Для полностью воспроизводимых тестов и работы без сети API-тесты переключают
`use_osrm = False`; в этом режиме используется детерминированный
`CoordinateRoutingProvider`.
