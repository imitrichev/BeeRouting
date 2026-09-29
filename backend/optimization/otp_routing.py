"""Уточнение отдельных дуг общественного транспорта через OpenTripPlanner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time as datetime_time, timedelta
import json
import math
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


OTP_TRIP_QUERY = """
query Trip(
    $fromLat: Float!, $fromLon: Float!,
    $toLat: Float!, $toLon: Float!, $dateTime: DateTime!
) {
  trip(
    from: {coordinates: {latitude: $fromLat, longitude: $fromLon}}
    to: {coordinates: {latitude: $toLat, longitude: $toLon}}
    dateTime: $dateTime
    arriveBy: false
    numTripPatterns: 3
    modes: {
      accessMode: foot
      egressMode: foot
      transportModes: [
        {transportMode: bus}
        {transportMode: metro}
        {transportMode: tram}
        {transportMode: rail}
      ]
    }
  ) {
    tripPatterns {
      duration
      legs { distance }
    }
  }
}
"""


@dataclass(frozen=True, slots=True)
class OTPRoute:
    """Лучший найденный OTP маршрут между двумя точками."""

    duration_minutes: int  # Полное время с ожиданием, пересадками и пешими участками.
    distance_km: float  # Сумма расстояний всех участков маршрута.


@dataclass(slots=True)
class OTPRouteCache:
    """Постоянный SQLite-кэш успешных и пустых ответов OTP."""

    path: Path | None

    def get(self, cache_key: str) -> tuple[str, OTPRoute | None] | None:
        """Возвращает ``ok``/``no_route`` либо ``None`` при отсутствии записи."""
        if self.path is None:
            return None
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT status, duration_minutes, distance_km "
                    "FROM otp_routes WHERE cache_key = ?",
                    (cache_key,),
                ).fetchone()
        except (OSError, sqlite3.Error):
            return None
        if row is None:
            return None
        status, duration_minutes, distance_km = row
        if status == "no_route":
            return status, None
        return status, OTPRoute(int(duration_minutes), float(distance_km))

    def put(self, cache_key: str, status: str, route: OTPRoute | None) -> None:
        """Сохраняет маршрут или отрицательный результат ``no_route``."""
        if self.path is None:
            return
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO otp_routes "
                    "(cache_key, status, duration_minutes, distance_km) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        cache_key,
                        status,
                        route.duration_minutes if route is not None else None,
                        route.distance_km if route is not None else None,
                    ),
                )
        except (OSError, sqlite3.Error):
            # Недоступный кэш не должен отключать маршрутизацию и fallback.
            return

    def _connect(self) -> sqlite3.Connection:
        """Открывает кэш и при первом обращении создаёт его схему."""
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS otp_routes ("
            "cache_key TEXT PRIMARY KEY, "
            "status TEXT NOT NULL, "
            "duration_minutes INTEGER, "
            "distance_km REAL"
            ")"
        )
        return connection


@dataclass(slots=True)
class OTPRoutingClient:
    """Запрашивает отдельные пары OTP и безопасно возвращает ``None``.

    ``None`` означает, что вызывающий код обязан сохранить существующий
    fallback ``OSRM driving × 2``. После сетевой или GraphQL-ошибки клиент
    отключается до конца расчёта, чтобы один недоступный сервис не создавал
    десятки последовательных тайм-аутов.
    """

    endpoint: str
    service_date: date
    timezone_name: str = "Europe/Moscow"
    bucket_minutes: int = 30
    timeout_seconds: float = 4.0
    cache: OTPRouteCache = field(default_factory=lambda: OTPRouteCache(None))
    _disabled: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        """Проверяет параметры времени и endpoint."""
        self.endpoint = self.endpoint.rstrip("/")
        if not self.endpoint:
            raise ValueError("OTP endpoint не должен быть пустым")
        if self.bucket_minutes <= 0 or 1_440 % self.bucket_minutes != 0:
            raise ValueError("OTP bucket_minutes должен делить сутки без остатка")
        if self.timeout_seconds <= 0:
            raise ValueError("OTP timeout_seconds должен быть положительным")
        try:
            ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Неизвестный часовой пояс OTP: {self.timezone_name}") from exc

    def get_route(
        self,
        from_coordinates: tuple[float, float],
        to_coordinates: tuple[float, float],
        departure_minutes: int,
    ) -> OTPRoute | None:
        """Возвращает лучший маршрут пары или ``None`` для fallback."""
        if self._disabled or from_coordinates == to_coordinates:
            return None
        bucket = min(1_439, max(0, departure_minutes))
        bucket -= bucket % self.bucket_minutes
        departure = datetime.combine(
            self.service_date,
            datetime_time.min,
            tzinfo=ZoneInfo(self.timezone_name),
        ) + timedelta(minutes=bucket)
        cache_key = self._cache_key(
            from_coordinates,
            to_coordinates,
            departure.isoformat(),
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached[1]

        payload = {
            "query": OTP_TRIP_QUERY,
            "variables": {
                "fromLat": from_coordinates[0],
                "fromLon": from_coordinates[1],
                "toLat": to_coordinates[0],
                "toLon": to_coordinates[1],
                "dateTime": departure.isoformat(),
            },
        }
        request = urllib_request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                response_payload = json.load(response)
        except (
            OSError,
            urllib_error.HTTPError,
            urllib_error.URLError,
            json.JSONDecodeError,
        ):
            self._disabled = True
            return None
        if not isinstance(response_payload, Mapping) or response_payload.get("errors"):
            self._disabled = True
            return None

        data = response_payload.get("data")
        trip = data.get("trip") if isinstance(data, Mapping) else None
        patterns = trip.get("tripPatterns", []) if isinstance(trip, Mapping) else []
        if not isinstance(patterns, list):
            self._disabled = True
            return None
        routes = [self._parse_pattern(pattern) for pattern in patterns]
        valid_routes = [route for route in routes if route is not None]
        if not valid_routes:
            # HTTP 200 с пустым tripPatterns — нормальный ответ за пределами
            # покрытия московского GTFS. Его важно отрицательно кэшировать.
            self.cache.put(cache_key, "no_route", None)
            return None
        route = min(valid_routes, key=lambda item: item.duration_minutes)
        self.cache.put(cache_key, "ok", route)
        return route

    @staticmethod
    def _parse_pattern(pattern: Any) -> OTPRoute | None:
        """Проверяет один tripPattern и переводит секунды/метры в доменные единицы."""
        if not isinstance(pattern, Mapping):
            return None
        duration = pattern.get("duration")
        legs = pattern.get("legs")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(float(duration))
            or duration <= 0
            or not isinstance(legs, list)
            or not legs
        ):
            return None
        distance_meters = 0.0
        for leg in legs:
            if not isinstance(leg, Mapping):
                return None
            distance = leg.get("distance")
            if (
                isinstance(distance, bool)
                or not isinstance(distance, (int, float))
                or not math.isfinite(float(distance))
                or distance < 0
            ):
                return None
            distance_meters += float(distance)
        return OTPRoute(
            duration_minutes=max(1, math.ceil(float(duration) / 60)),
            distance_km=distance_meters / 1_000,
        )

    def _cache_key(
        self,
        from_coordinates: tuple[float, float],
        to_coordinates: tuple[float, float],
        departure_bucket: str,
    ) -> str:
        """Формирует устойчивый ключ пары, даты и 30-минутного интервала."""
        coordinates = (*from_coordinates, *to_coordinates)
        return "|".join(
            (
                *(f"{coordinate:.6f}" for coordinate in coordinates),
                departure_bucket,
                self.endpoint,
            )
        )


def create_otp_client_from_environment() -> OTPRoutingClient | None:
    """Создаёт OTP-клиент либо отключает уточнение через ``OTP_ENABLED``."""
    enabled = os.getenv("OTP_ENABLED", "true").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return None
    cache_value = os.getenv(
        "OTP_CACHE_PATH",
        str(Path(__file__).resolve().parents[2] / ".cache" / "otp" / "otp_routes.sqlite3"),
    ).strip()
    cache_path = (
        None
        if cache_value.lower() in {"", "off", "none"}
        else Path(cache_value)
    )
    try:
        service_date = date.fromisoformat(
            os.getenv("OTP_SERVICE_DATE", "2026-08-17")
        )
    except ValueError as exc:
        raise ValueError("OTP_SERVICE_DATE должен иметь формат YYYY-MM-DD") from exc
    return OTPRoutingClient(
        endpoint=os.getenv(
            "OTP_URL",
            "http://127.0.0.1:8081/otp/transmodel/v3",
        ),
        service_date=service_date,
        timezone_name=os.getenv("OTP_TIMEZONE", "Europe/Moscow"),
        bucket_minutes=int(os.getenv("OTP_TIME_BUCKET_MINUTES", "30")),
        timeout_seconds=float(os.getenv("OTP_TIMEOUT_SECONDS", "4")),
        cache=OTPRouteCache(cache_path),
    )
