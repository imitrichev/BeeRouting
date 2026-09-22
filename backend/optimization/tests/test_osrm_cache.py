"""Проверки постоянного кэша между независимыми экземплярами provider."""

from dataclasses import replace
from unittest.mock import patch

import pytest

from backend.optimization import OSRMRoutingProvider, VehicleType
from backend.optimization.tests.test_routing_provider import _response


@pytest.fixture
def provider(tmp_path):
    """Создаёт изолированный файловый кэш, не затрагивая рабочие данные."""
    return OSRMRoutingProvider(
        coordinates={"a": (55.0, 37.0), "b": (55.1, 37.1)},
        base_url="https://osrm.test",
        pair_cache_path=tmp_path / "pairs.sqlite3",
        matrix_cache_path=tmp_path / "matrices",
    )


def populate(provider):
    """Заполняет кэш асимметричной таблицей для двух точек."""
    with patch("backend.optimization.routing_provider.urllib_request.urlopen", return_value=_response({
        "code": "Ok", "durations": [[0, 61], [180, 0]],
        "distances": [[0, 1200], [2300, 0]],
    })):
        return provider.get_travel_time_matrix(("a", "b"))


def test_npz_survives_provider_restart(provider):
    """Новый provider читает NPZ без HTTP и даже без SQLite."""
    expected = populate(provider)
    with patch("backend.optimization.routing_provider.urllib_request.urlopen", side_effect=AssertionError("network")):
        fresh = replace(provider, pair_cache_path=None)
        assert fresh.get_travel_time_matrix(("a", "b")) == expected
        assert fresh.get_distance_matrix(("a", "b"))["b"]["a"] == 2.3


def test_sqlite_reorders_pairs_and_applies_public_multiplier_once(provider):
    """SQLite восстанавливает иной порядок; коэффициент не округляется заранее."""
    populate(provider)
    with patch("backend.optimization.routing_provider.urllib_request.urlopen", side_effect=AssertionError("network")):
        fresh = replace(provider, matrix_cache_path=None)
        result = fresh.get_travel_time_matrix(("b", "a"), VehicleType.PUBLIC_TRANSPORT)
        assert result["a"]["b"] == 3  # ceil(61 * 2 / 60), а не 2 * ceil(61 / 60).
        assert result["b"]["a"] == 6


@pytest.mark.parametrize("change", ["coordinates", "endpoint", "profile"])
def test_changed_graph_or_coordinates_do_not_use_stale_cache(provider, change):
    """Изменение источника или координат требует новых дорожных данных."""
    populate(provider)
    changes = {
        "coordinates": {"coordinates": {"a": (55.2, 37.0), "b": (55.1, 37.1)}},
        "endpoint": {"base_url": "https://another.test"},
        "profile": {"profiles": {VehicleType.CAR: "walking"}},
    }
    with patch("backend.optimization.routing_provider.urllib_request.urlopen", side_effect=AssertionError("cache miss")):
        with pytest.raises(AssertionError, match="cache miss"):
            replace(provider, **changes[change]).get_travel_time_matrix(("a", "b"))


def test_extension_keeps_known_pairs_and_caches_new_pairs(provider):
    """Добавление точки дополняет пары, не перезаписывая старые значения."""
    populate(provider)
    fresh = replace(provider, coordinates={**provider.coordinates, "c": (55.2, 37.2)})
    with patch("backend.optimization.routing_provider.urllib_request.urlopen", return_value=_response({
        "code": "Ok", "durations": [[0, 999, 120], [999, 0, 180], [240, 300, 0]],
        "distances": [[0, 9999, 1200], [9999, 0, 1800], [2400, 3000, 0]],
    })):
        result = fresh.get_travel_time_matrix(("a", "b", "c"))
    assert result["a"]["b"] == 2
    assert result["c"]["a"] == 4
    with patch("backend.optimization.routing_provider.urllib_request.urlopen", side_effect=AssertionError("network")):
        assert replace(fresh, matrix_cache_path=None).get_travel_time_matrix(("c", "a"))["c"]["a"] == 4


def test_broken_npz_is_restored_from_sqlite(provider):
    """Повреждённый NPZ не требует сети, если сохранился SQLite."""
    populate(provider)
    next(provider.matrix_cache_path.glob("*.npz")).write_bytes(b"broken archive")
    with patch("backend.optimization.routing_provider.urllib_request.urlopen", side_effect=AssertionError("network")):
        assert replace(provider).get_travel_time_matrix(("a", "b"))["a"]["b"] == 2
