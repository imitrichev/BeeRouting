"""Тесты точечного уточнения маршрутов через OpenTripPlanner."""

from datetime import date
import io
import json
from unittest.mock import patch

from backend.optimization import OTPRouteCache, OTPRoutingClient


class _JsonResponse(io.BytesIO):
    """Минимальный HTTP-ответ для ``urlopen``."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def _response(payload: dict) -> _JsonResponse:
    """Кодирует GraphQL JSON как HTTP body."""
    return _JsonResponse(json.dumps(payload).encode("utf-8"))


def test_otp_selects_fastest_pattern_and_reuses_sqlite_cache(tmp_path) -> None:
    """Успешная пара сохраняется по координатам, дате и временному bucket."""
    payload = {
        "data": {
            "trip": {
                "tripPatterns": [
                    {"duration": 1_800, "legs": [{"distance": 8_000}]},
                    {
                        "duration": 1_200,
                        "legs": [{"distance": 1_000}, {"distance": 5_500}],
                    },
                ]
            }
        }
    }
    cache_path = tmp_path / "otp.sqlite3"
    client = OTPRoutingClient(
        endpoint="http://otp.test/otp/transmodel/v3",
        service_date=date(2026, 8, 17),
        cache=OTPRouteCache(cache_path),
    )

    with patch(
        "backend.optimization.otp_routing.urllib_request.urlopen",
        return_value=_response(payload),
    ) as urlopen:
        first = client.get_route((55.7, 37.6), (55.8, 37.7), 8 * 60 + 17)

    assert first is not None
    assert first.duration_minutes == 20
    assert first.distance_km == 6.5
    assert urlopen.call_count == 1

    # 08:29 попадает в тот же 30-минутный bucket и читается новым клиентом
    # из постоянного кэша без обращения в сеть.
    cached_client = OTPRoutingClient(
        endpoint="http://otp.test/otp/transmodel/v3",
        service_date=date(2026, 8, 17),
        cache=OTPRouteCache(cache_path),
    )
    with patch(
        "backend.optimization.otp_routing.urllib_request.urlopen"
    ) as cached_urlopen:
        second = cached_client.get_route(
            (55.7, 37.6),
            (55.8, 37.7),
            8 * 60 + 29,
        )

    assert second == first
    cached_urlopen.assert_not_called()


def test_otp_empty_patterns_are_negatively_cached(tmp_path) -> None:
    """HTTP 200 без маршрута, в том числе за Москвой, включает fallback."""
    payload = {"data": {"trip": {"tripPatterns": []}}}
    client = OTPRoutingClient(
        endpoint="http://otp.test/otp/transmodel/v3",
        service_date=date(2026, 8, 17),
        cache=OTPRouteCache(tmp_path / "otp.sqlite3"),
    )

    with patch(
        "backend.optimization.otp_routing.urllib_request.urlopen",
        return_value=_response(payload),
    ) as urlopen:
        assert client.get_route((54.9, 38.1), (54.8, 38.2), 600) is None
        assert client.get_route((54.9, 38.1), (54.8, 38.2), 610) is None

    assert urlopen.call_count == 1


def test_otp_transport_error_disables_requests_for_current_run() -> None:
    """После недоступности OTP остальные дуги сразу используют fallback."""
    client = OTPRoutingClient(
        endpoint="http://otp.test/otp/transmodel/v3",
        service_date=date(2026, 8, 17),
    )

    with patch(
        "backend.optimization.otp_routing.urllib_request.urlopen",
        side_effect=OSError("OTP недоступен"),
    ) as urlopen:
        assert client.get_route((55.7, 37.6), (55.8, 37.7), 600) is None
        assert client.get_route((55.8, 37.7), (55.9, 37.8), 630) is None

    assert urlopen.call_count == 1

