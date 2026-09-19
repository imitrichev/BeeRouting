"""Тесты внешнего OSRM provider без сетевых запросов."""

import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

from backend.optimization import (
    CoordinateRoutingProvider,
    OSRMRoutingProvider,
    VehicleType,
    create_osrm_provider_from_environment,
)


class _JsonResponse(io.BytesIO):
    """Минимальный объект ответа, совместимый с ``urlopen`` и ``json.load``."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def _response(payload: dict) -> _JsonResponse:
    """Кодирует тестовый ответ OSRM в формат файлового HTTP-ответа."""
    return _JsonResponse(json.dumps(payload).encode("utf-8"))


def test_osrm_table_returns_minutes_and_kilometers_and_uses_cache() -> None:
    """Один table response даёт обе матрицы, повторный вызов не идёт в сеть."""
    provider = OSRMRoutingProvider(
        coordinates={"a": (55.0, 37.0), "b": (55.1, 37.1)},
        base_url="https://osrm.test",
    )
    table_payload = {
        "code": "Ok",
        "durations": [[0, 61], [60, 0]],
        "distances": [[0, 1234], [1200, 0]],
    }

    with patch(
        "backend.optimization.routing_provider.urllib_request.urlopen",
        return_value=_response(table_payload),
    ) as urlopen:
        time_matrix = provider.get_travel_time_matrix(("a", "b"), VehicleType.CAR)
        distance_matrix = provider.get_distance_matrix(("a", "b"), VehicleType.CAR)

    assert time_matrix["a"]["b"] == 2  # OSRM 61 секунд округляются вверх до 2 минут.
    assert time_matrix["b"]["a"] == 1
    assert distance_matrix["a"]["b"] == 1.234
    assert distance_matrix["b"]["a"] == 1.2
    assert urlopen.call_count == 1
    assert "/table/v1/driving/" in urlopen.call_args.args[0]


def test_osrm_route_returns_geojson_geometry_and_caches_same_request() -> None:
    """Route service возвращает geometry, которую можно напрямую показать MapLibre."""
    provider = OSRMRoutingProvider(
        coordinates={"a": (55.0, 37.0), "b": (55.1, 37.1)},
        base_url="https://osrm.test",
    )
    route_payload = {
        "code": "Ok",
        "routes": [
            {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[37.0, 55.0], [37.1, 55.1]],
                }
            }
        ],
    }

    with patch(
        "backend.optimization.routing_provider.urllib_request.urlopen",
        return_value=_response(route_payload),
    ) as urlopen:
        first = provider.get_route_geometry(("a", "b"), VehicleType.BICYCLE)
        second = provider.get_route_geometry(("a", "b"), VehicleType.BICYCLE)

    assert first == second == route_payload["routes"][0]["geometry"]
    assert urlopen.call_count == 1
    assert "/route/v1/cycling/" in urlopen.call_args.args[0]


def test_public_transport_has_explicit_driving_fallback_profile() -> None:
    """PUBLIC_TRANSPORT использует driving fallback и удвоенное время."""
    provider = OSRMRoutingProvider(
        coordinates={"a": (55.0, 37.0), "b": (55.1, 37.1)},
        base_url="https://osrm.test",
    )
    payload = {"code": "Ok", "durations": [[0, 60], [60, 0]], "distances": [[0, 1], [1, 0]]}

    with patch(
        "backend.optimization.routing_provider.urllib_request.urlopen",
        return_value=_response(payload),
    ) as urlopen:
        matrix = provider.get_travel_time_matrix(
            ("a", "b"), VehicleType.PUBLIC_TRANSPORT
        )

    assert "/table/v1/driving/" in urlopen.call_args.args[0]
    assert matrix["a"]["b"] == 2


def test_coordinate_provider_uses_vehicle_specific_demo_speeds() -> None:
    """Fallback-матрица не должна выдавать автомобилю и WALK одну скорость."""

    provider = CoordinateRoutingProvider(
        coordinates={"base": (55.0, 37.0), "task": (55.1, 37.0)},
        speed_km_per_hour=30.0,
    )
    car = provider.get_travel_time_matrix(("base", "task"), VehicleType.CAR)
    walk = provider.get_travel_time_matrix(("base", "task"), VehicleType.WALK)
    bicycle = provider.get_travel_time_matrix(("base", "task"), VehicleType.BICYCLE)
    public_transport = provider.get_travel_time_matrix(
        ("base", "task"), VehicleType.PUBLIC_TRANSPORT
    )

    assert car["base"]["task"] < bicycle["base"]["task"] < walk["base"]["task"]
    # Округление минут выполняется после умножения, поэтому допускается
    # разница в одну минуту относительно удвоенного округлённого CAR-времени.
    assert abs(public_transport["base"]["task"] - car["base"]["task"] * 2) <= 1


def test_default_osrm_factory_uses_separate_road_graphs() -> None:
    """WALK и BICYCLE не должны незаметно обращаться к автомобильному OSRM."""
    with patch.dict("os.environ", {}, clear=True):
        provider = create_osrm_provider_from_environment(
            {"a": (55.0, 37.0), "b": (55.1, 37.1)},
            request_timeout_seconds=3,
        )

    walk_url = provider._url(
        "table", provider._profile(VehicleType.WALK), ("a", "b"), {}, VehicleType.WALK
    )
    bicycle_url = provider._url(
        "table", provider._profile(VehicleType.BICYCLE), ("a", "b"), {}, VehicleType.BICYCLE
    )
    car_url = provider._url(
        "table", provider._profile(VehicleType.CAR), ("a", "b"), {}, VehicleType.CAR
    )

    assert "/routed-foot/table/v1/driving/" in walk_url
    assert "/routed-bike/table/v1/driving/" in bicycle_url
    assert "/router.project-osrm.org/table/v1/driving/" in car_url
    assert walk_url != car_url
    assert bicycle_url != car_url


def test_osrm_retries_rate_limit_using_retry_after() -> None:
    """Краткий HTTP 429 повторяется после паузы, указанной OSRM."""
    provider = OSRMRoutingProvider(
        coordinates={"a": (55.0, 37.0), "b": (55.1, 37.1)},
        base_url="https://osrm.test",
        max_rate_limit_retries=1,
    )
    payload = {
        "code": "Ok",
        "durations": [[0, 60], [60, 0]],
        "distances": [[0, 1], [1, 0]],
    }
    rate_limit_error = HTTPError(
        "https://osrm.test/table",
        429,
        "Too Many Requests",
        {"Retry-After": "0.25"},
        None,
    )

    with (
        patch(
            "backend.optimization.routing_provider.urllib_request.urlopen",
            side_effect=[rate_limit_error, _response(payload)],
        ) as urlopen,
        patch("backend.optimization.routing_provider.time.sleep") as sleep,
    ):
        matrix = provider.get_travel_time_matrix(("a", "b"), VehicleType.CAR)

    assert matrix["a"]["b"] == 1
    assert urlopen.call_count == 2
    sleep.assert_called_once_with(0.25)
