"""Интерфейс внешнего источника матрицы времени движения."""

from dataclasses import dataclass, field
import math
import json
import os
import time
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from .models import VehicleType


@runtime_checkable
class RoutingProvider(Protocol):
    """Контракт получения готовых матриц времени и расстояния.

    Провайдер только поставляет данные маршрутизации. Он не назначает заявки
    и не строит маршруты: это делает выбранная реализация ``RouteOptimizer``.
    """

    def get_travel_time_matrix(
        self,
        location_ids: Iterable[str],  # Локации, для которых нужна подматрица.
        vehicle_type: VehicleType = VehicleType.CAR,  # Тип транспорта для профиля маршрутизации.
    ) -> Mapping[str, Mapping[str, int]]:
        """Возвращает время движения между переданными локациями в минутах."""

    def get_distance_matrix(
        self,
        location_ids: Iterable[str],  # Те же локации, что и для времени движения.
        vehicle_type: VehicleType = VehicleType.CAR,  # Тип транспорта для профиля маршрутизации.
    ) -> Mapping[str, Mapping[str, float]]:
        """Возвращает расстояние между переданными локациями в километрах."""

    def get_route_geometry(
        self,
        location_ids: Iterable[str],  # Упорядоченные точки маршрута, включая старт.
        vehicle_type: VehicleType = VehicleType.CAR,  # Тип транспорта для профиля маршрута.
    ) -> Mapping[str, Any] | None:
        """Возвращает GeoJSON geometry маршрута или ``None``."""


@dataclass(frozen=True, slots=True)
class InMemoryRoutingProvider:
    """Детерминированный провайдер с двумя заранее заданными матрицами."""

    travel_time_matrix: Mapping[str, Mapping[str, int]]  # [откуда][куда]: время движения в минутах.
    distance_matrix: Mapping[str, Mapping[str, float]]  # [откуда][куда]: расстояние в километрах.

    def get_travel_time_matrix(
        self,
        location_ids: Iterable[str],  # Упорядоченный набор запрашиваемых локаций.
        vehicle_type: VehicleType = VehicleType.CAR,  # In-memory provider этот параметр не использует.
    ) -> Mapping[str, Mapping[str, int]]:
        """Возвращает копию подматрицы времени и проверяет её полноту."""
        # dict.fromkeys сохраняет порядок входных локаций и одновременно
        # убирает повторы, чтобы в результате получить квадратную подматрицу.
        requested_locations = tuple(dict.fromkeys(location_ids))
        matrix = {
            from_location: dict(to_locations)
            for from_location, to_locations in self.travel_time_matrix.items()
        }
        missing_origins = set(requested_locations) - matrix.keys()
        if missing_origins:
            raise ValueError(
                f"В routing provider отсутствуют исходные локации: "
                f"{sorted(missing_origins)}"
            )
        for from_location in requested_locations:
            missing_destinations = set(requested_locations) - matrix[
                from_location
            ].keys()
            if missing_destinations:
                raise ValueError(
                    f"В routing provider отсутствуют назначения из "
                    f"{from_location}: {sorted(missing_destinations)}"
                )
        return {
            from_location: {
                to_location: matrix[from_location][to_location]
                for to_location in requested_locations
            }
            for from_location in requested_locations
        }

    def get_distance_matrix(
        self,
        location_ids: Iterable[str],  # Упорядоченный набор запрашиваемых локаций.
        vehicle_type: VehicleType = VehicleType.CAR,  # In-memory provider этот параметр не использует.
    ) -> Mapping[str, Mapping[str, float]]:
        """Возвращает копию подматрицы расстояний и проверяет её полноту."""
        # Подматрица строится тем же способом, что и для времени: обе матрицы
        # должны описывать одинаковые строки и столбцы.
        requested_locations = tuple(dict.fromkeys(location_ids))
        matrix = {
            from_location: dict(to_locations)
            for from_location, to_locations in self.distance_matrix.items()
        }
        missing_origins = set(requested_locations) - matrix.keys()
        if missing_origins:
            raise ValueError(
                f"В routing provider отсутствуют исходные локации: "
                f"{sorted(missing_origins)}"
            )
        for from_location in requested_locations:
            missing_destinations = set(requested_locations) - matrix[
                from_location
            ].keys()
            if missing_destinations:
                raise ValueError(
                    f"В routing provider отсутствуют назначения из "
                    f"{from_location}: {sorted(missing_destinations)}"
                )
        return {
            from_location: {
                to_location: matrix[from_location][to_location]
                for to_location in requested_locations
            }
            for from_location in requested_locations
        }

    def get_route_geometry(
        self,
        location_ids: Iterable[str],  # Упорядоченные точки маршрута.
        vehicle_type: VehicleType = VehicleType.CAR,  # In-memory provider не строит geometry без координат.
    ) -> Mapping[str, Any] | None:
        """Возвращает ``None``: у матриц нет координат для построения линии."""
        return None


@dataclass(frozen=True, slots=True)
class CoordinateRoutingProvider:
    """Детерминированный provider для демо без внешнего картографического API.

    Расстояние считается по прямой между координатами, а время — по средней
    скорости, зависящей от типа транспорта. Это fallback для тестов и работы
    без сети; расстояние и geometry здесь не являются расстоянием по дорогам.
    Класс нужен для локального MVP и тестового набора; реальный сетевой
    провайдер можно позже подключить через тот же ``RoutingProvider``.
    """

    coordinates: Mapping[str, tuple[float, float]]  # Координаты локаций: latitude, longitude.
    speed_km_per_hour: float = 30.0  # Условная скорость для расчёта демонстрационного travel time.
    walk_speed_km_per_hour: float = 5.0  # Средняя скорость пешего перемещения.
    bicycle_speed_km_per_hour: float = 15.0  # Средняя скорость велосипеда.
    public_transport_time_multiplier: float = 2.0  # Дополнительный коэффициент времени общественного транспорта.

    def get_travel_time_matrix(
        self,
        location_ids: Iterable[str],  # Упорядоченный набор локаций для подматрицы.
        vehicle_type: VehicleType = VehicleType.CAR,  # Выбирает демонстрационную скорость транспорта.
    ) -> Mapping[str, Mapping[str, int]]:
        """Возвращает детерминированное время движения в минутах."""
        _, travel_time_matrix = self._build_matrices(location_ids, vehicle_type)
        return travel_time_matrix

    def get_distance_matrix(
        self,
        location_ids: Iterable[str],  # Тот же набор локаций, что и для времени.
        vehicle_type: VehicleType = VehicleType.CAR,  # Тип транспорта не меняет расстояние по прямой.
    ) -> Mapping[str, Mapping[str, float]]:
        """Возвращает расстояние между локациями в километрах."""
        distance_matrix, _ = self._build_matrices(location_ids, vehicle_type)
        return distance_matrix

    def get_route_geometry(
        self,
        location_ids: Iterable[str],  # Упорядоченные точки маршрута, включая старт.
        vehicle_type: VehicleType = VehicleType.CAR,  # Тип транспорта не меняет прямую geometry.
    ) -> Mapping[str, Any] | None:
        """Возвращает прямую GeoJSON-линию между переданными координатами."""
        requested_locations = tuple(dict.fromkeys(location_ids))
        missing_locations = set(requested_locations) - self.coordinates.keys()
        if missing_locations:
            raise ValueError(
                f"Отсутствуют координаты локаций: {sorted(missing_locations)}"
            )
        return {
            "type": "LineString",
            "coordinates": [
                [self.coordinates[location][1], self.coordinates[location][0]]
                for location in requested_locations
            ],
        }

    def _build_matrices(
        self,
        location_ids: Iterable[str],
        vehicle_type: VehicleType,
    ) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, int]]]:
        """Строит обе матрицы для запрошенного набора координат."""
        if self.speed_km_per_hour <= 0:
            raise ValueError("speed_km_per_hour должен быть положительным")
        if self.walk_speed_km_per_hour <= 0:
            raise ValueError("walk_speed_km_per_hour должен быть положительным")
        if self.bicycle_speed_km_per_hour <= 0:
            raise ValueError("bicycle_speed_km_per_hour должен быть положительным")
        if self.public_transport_time_multiplier <= 0:
            raise ValueError("public_transport_time_multiplier должен быть положительным")
        requested_locations = tuple(dict.fromkeys(location_ids))
        missing_locations = set(requested_locations) - self.coordinates.keys()
        if missing_locations:
            raise ValueError(
                f"Отсутствуют координаты локаций: {sorted(missing_locations)}"
            )
        distance_matrix: dict[str, dict[str, float]] = {}
        travel_time_matrix: dict[str, dict[str, int]] = {}
        for source in requested_locations:
            distance_matrix[source] = {}
            travel_time_matrix[source] = {}
            for destination in requested_locations:
                distance = _haversine_km(
                    *self.coordinates[source],
                    *self.coordinates[destination],
                )
                distance_matrix[source][destination] = distance
                if vehicle_type == VehicleType.WALK:
                    speed = self.walk_speed_km_per_hour
                elif vehicle_type == VehicleType.BICYCLE:
                    speed = self.bicycle_speed_km_per_hour
                elif vehicle_type == VehicleType.PUBLIC_TRANSPORT:
                    # Упрощённая модель: общественный транспорт в два раза
                    # дольше автомобиля, без расписаний и пересадок.
                    speed = self.speed_km_per_hour / self.public_transport_time_multiplier
                else:
                    speed = self.speed_km_per_hour
                base_minutes = distance / speed * 60
                travel_time_matrix[source][destination] = (
                    0 if distance == 0 else max(1, math.ceil(base_minutes))
                )
        return distance_matrix, travel_time_matrix


def _haversine_km(
    source_latitude: float,
    source_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> float:
    """Вычисляет расстояние по поверхности Земли между координатами."""
    earth_radius_km = 6_371.0
    latitude_1 = math.radians(source_latitude)
    latitude_2 = math.radians(destination_latitude)
    delta_latitude = math.radians(destination_latitude - source_latitude)
    delta_longitude = math.radians(destination_longitude - source_longitude)
    haversine = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(latitude_1)
        * math.cos(latitude_2)
        * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * earth_radius_km * math.asin(math.sqrt(haversine))


@dataclass(frozen=True, slots=True)
class OSRMRoutingProvider:
    """Получает матрицы и GeoJSON geometry из OSRM HTTP API.

    OSRM использует профили маршрутизации. Профиль передаётся отдельно для
    каждого типа транспорта. Кроме профиля
    можно указать отдельный ``base_urls``: это нужно, когда пеший и
    велосипедный графы работают на отдельных экземплярах OSRM. Профиль
    ``PUBLIC_TRANSPORT`` заменяется на ``driving`` и получает коэффициент
    времени 2.0: стандартный OSRM не моделирует расписания и пересадки
    общественного транспорта. Это явное приближение; при наличии собственного
    профиля его можно передать через ``profiles``.
    """

    coordinates: Mapping[str, tuple[float, float]]  # Координаты локаций: latitude, longitude.
    base_url: str = "https://router.project-osrm.org"  # Адрес OSRM HTTP API без завершающего слеша.
    request_timeout_seconds: float = 15.0  # Тайм-аут одного HTTP-запроса к OSRM.
    max_rate_limit_retries: int = 2  # Сколько раз повторить запрос после HTTP 429.
    rate_limit_backoff_seconds: float = 2.0  # Базовая пауза между повторами при HTTP 429.
    public_transport_time_multiplier: float = 2.0  # Во сколько раз увеличивать время public относительно профиля OSRM.
    profiles: Mapping[VehicleType, str] = field(
        default_factory=lambda: {
            VehicleType.CAR: "driving",
            VehicleType.WALK: "walking",
            VehicleType.BICYCLE: "cycling",
            VehicleType.PUBLIC_TRANSPORT: "driving",
        }
    )  # Профиль OSRM для каждого доменного типа транспорта.
    base_urls: Mapping[VehicleType, str] = field(default_factory=dict)  # Отдельный HTTP endpoint OSRM для каждого типа транспорта.
    _cache: dict[str, Mapping[str, Any]] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
    )  # Простое in-memory кэширование ответов по полному URL запроса.

    def get_travel_time_matrix(
        self,
        location_ids: Iterable[str],  # Локации, для которых нужна матрица.
        vehicle_type: VehicleType = VehicleType.CAR,  # Выбирает профиль OSRM.
    ) -> Mapping[str, Mapping[str, int]]:
        """Получает таблицу времени OSRM и переводит секунды в минуты."""
        durations, _ = self._get_table(location_ids, vehicle_type)
        return durations

    def get_distance_matrix(
        self,
        location_ids: Iterable[str],  # Те же локации, что и для времени.
        vehicle_type: VehicleType = VehicleType.CAR,  # Выбирает профиль OSRM.
    ) -> Mapping[str, Mapping[str, float]]:
        """Получает таблицу расстояний OSRM и переводит метры в километры."""
        _, distances = self._get_table(location_ids, vehicle_type)
        return distances

    def get_route_geometry(
        self,
        location_ids: Iterable[str],  # Упорядоченные точки маршрута, включая старт.
        vehicle_type: VehicleType = VehicleType.CAR,  # Выбирает профиль OSRM.
    ) -> Mapping[str, Any] | None:
        """Получает полную geometry маршрута в формате GeoJSON."""
        requested_locations = tuple(location_ids)
        if len(requested_locations) < 2:
            return None
        url = self._url(
            service="route",
            profile=self._profile(vehicle_type),
            location_ids=requested_locations,
            query={"overview": "full", "geometries": "geojson", "steps": "false"},
            vehicle_type=vehicle_type,
        )
        payload = self._get_json(url)
        routes = payload.get("routes")
        if payload.get("code") != "Ok" or not routes:
            raise RoutingProviderError(
                f"OSRM route не построил маршрут: {payload.get('code', 'Unknown')}"
            )
        geometry = routes[0].get("geometry")
        if not isinstance(geometry, dict):
            raise RoutingProviderError("OSRM не вернул GeoJSON geometry маршрута")
        return geometry

    def _get_table(
        self,
        location_ids: Iterable[str],
        vehicle_type: VehicleType,
    ) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, float]]]:
        """Запрашивает одну OSRM table и преобразует обе её матрицы."""
        requested_locations = tuple(location_ids)
        if not requested_locations:
            return {}, {}
        if self.public_transport_time_multiplier <= 0:
            raise RoutingProviderError(
                "public_transport_time_multiplier должен быть положительным"
            )
        url = self._url(
            service="table",
            profile=self._profile(vehicle_type),
            location_ids=requested_locations,
            query={"annotations": "duration,distance"},
            vehicle_type=vehicle_type,
        )
        payload = self._get_json(url)
        durations = payload.get("durations")
        distances = payload.get("distances")
        if payload.get("code") != "Ok" or not isinstance(durations, list) or not isinstance(distances, list):
            raise RoutingProviderError(
                f"OSRM table не построил матрицы: {payload.get('code', 'Unknown')}"
            )
        if len(durations) != len(requested_locations) or len(distances) != len(requested_locations):
            raise RoutingProviderError("OSRM вернул матрицы неправильного размера")

        time_matrix: dict[str, dict[str, int]] = {}
        distance_matrix: dict[str, dict[str, float]] = {}
        for row_index, source in enumerate(requested_locations):
            if not isinstance(durations[row_index], list) or not isinstance(distances[row_index], list):
                raise RoutingProviderError("OSRM вернул некорректную строку матрицы")
            time_matrix[source] = {}
            distance_matrix[source] = {}
            for column_index, destination in enumerate(requested_locations):
                duration_seconds = durations[row_index][column_index]
                distance_meters = distances[row_index][column_index]
                if duration_seconds is None or distance_meters is None:
                    raise RoutingProviderError(
                        f"OSRM не нашёл маршрут из {source} в {destination}"
                    )
                multiplier = (
                    self.public_transport_time_multiplier
                    if vehicle_type == VehicleType.PUBLIC_TRANSPORT
                    else 1.0
                )
                time_matrix[source][destination] = (
                    0
                    if duration_seconds == 0
                    else max(1, math.ceil(duration_seconds / 60 * multiplier))
                )
                distance_matrix[source][destination] = float(distance_meters) / 1000
        return time_matrix, distance_matrix

    def _profile(self, vehicle_type: VehicleType) -> str:
        """Возвращает профиль OSRM для фиксированного типа транспорта."""
        try:
            return self.profiles[vehicle_type]
        except KeyError as exc:
            raise RoutingProviderError(
                f"Для транспорта {vehicle_type.value} не задан профиль OSRM"
            ) from exc

    def _url(
        self,
        service: str,
        profile: str,
        location_ids: tuple[str, ...],
        query: Mapping[str, str],
        vehicle_type: VehicleType,
    ) -> str:
        """Собирает URL OSRM из координат и параметров запроса."""
        try:
            coordinates = ";".join(
                # OSRM принимает порядок longitude,latitude, тогда как domain
                # хранит координаты в привычном для API порядке latitude,longitude.
                f"{self.coordinates[location][1]},{self.coordinates[location][0]}"
                for location in location_ids
            )
        except KeyError as exc:
            raise RoutingProviderError(
                f"Для OSRM отсутствуют координаты локации {exc.args[0]}"
            ) from exc
        encoded_coordinates = urllib_parse.quote(coordinates, safe=";,.-")
        encoded_query = urllib_parse.urlencode(query)
        # У разных транспортных режимов могут быть разные серверы OSRM.
        # Например, routed-foot и routed-bike используют путь /v1/driving,
        # но строят маршрут по своим графам. Если отдельный endpoint не задан,
        # сохраняется обычное поведение: используется общий base_url.
        base_url = self.base_urls.get(vehicle_type, self.base_url)
        return f"{base_url.rstrip('/')}/{service}/v1/{profile}/{encoded_coordinates}?{encoded_query}"

    def _get_json(self, url: str) -> Mapping[str, Any]:
        """Возвращает JSON по URL, используя кэш одинаковых запросов."""
        cached = self._cache.get(url)
        if cached is not None:
            return cached
        for attempt in range(self.max_rate_limit_retries + 1):
            try:
                with urllib_request.urlopen(
                    url, timeout=self.request_timeout_seconds
                ) as response:
                    payload = json.load(response)
                break
            except urllib_error.HTTPError as exc:
                if exc.code != 429 or attempt >= self.max_rate_limit_retries:
                    if exc.code == 429:
                        raise RoutingProviderError(
                            "OSRM отклонил запрос с HTTP 429: превышен лимит "
                            "публичного сервиса. Подождите или используйте "
                            "собственный OSRM; повторные попытки исчерпаны."
                        ) from exc
                    raise RoutingProviderError(
                        f"Ошибка запроса к OSRM: HTTP {exc.code}"
                    ) from exc

                # OSRM может прислать Retry-After с требуемой паузой. Если
                # заголовка нет, используем экспоненциальную задержку 2, 4, ...
                # секунд, чтобы не усиливать ограничение частыми повторами.
                retry_after = exc.headers.get("Retry-After")
                try:
                    wait_seconds = float(retry_after) if retry_after else 0.0
                except (TypeError, ValueError):
                    wait_seconds = 0.0
                if wait_seconds <= 0:
                    wait_seconds = self.rate_limit_backoff_seconds * (2**attempt)
                time.sleep(wait_seconds)
            except (OSError, urllib_error.URLError, json.JSONDecodeError) as exc:
                raise RoutingProviderError(f"Ошибка запроса к OSRM: {exc}") from exc
        else:  # pragma: no cover - цикл завершается return или исключением.
            raise RoutingProviderError("OSRM не вернул ответ")
        if not isinstance(payload, dict):
            raise RoutingProviderError("OSRM вернул JSON не в виде объекта")
        self._cache[url] = payload
        return payload


def create_osrm_provider_from_environment(
    coordinates: Mapping[str, tuple[float, float]],
    request_timeout_seconds: float,
    base_url: str | None = None,
) -> OSRMRoutingProvider:
    """Создаёт OSRM provider с отдельными дорожными графами по режимам.

    Публичный ``router.project-osrm.org`` предоставляет автомобильный граф.
    Для пешего и велосипедного маршрута по умолчанию используются отдельные
    OSRM endpoints проекта OpenStreetMap. Если задан ``OSRM_BASE_URL``, он
    считается единым сервером с профилями ``driving``, ``walking`` и
    ``cycling`` — это удобно для собственного многопрофильного OSRM.

    Отдельные переменные ``OSRM_CAR_BASE_URL``, ``OSRM_WALK_BASE_URL``,
    ``OSRM_BICYCLE_BASE_URL`` и ``OSRM_PUBLIC_TRANSPORT_BASE_URL`` имеют
    приоритет. Имена профилей можно переопределить переменными
    ``OSRM_CAR_PROFILE``, ``OSRM_WALK_PROFILE`` и ``OSRM_BICYCLE_PROFILE``.
    Общественный транспорт остаётся приближением: автомобильный граф и
    удвоенное время.
    """
    common_base_url = base_url or os.getenv("OSRM_BASE_URL")
    has_common_profile_server = common_base_url is not None
    default_base_urls = {
        VehicleType.CAR: common_base_url or "https://router.project-osrm.org",
        VehicleType.WALK: common_base_url or "https://routing.openstreetmap.de/routed-foot",
        VehicleType.BICYCLE: common_base_url or "https://routing.openstreetmap.de/routed-bike",
        VehicleType.PUBLIC_TRANSPORT: common_base_url or "https://router.project-osrm.org",
    }
    environment_names = {
        VehicleType.CAR: "OSRM_CAR_BASE_URL",
        VehicleType.WALK: "OSRM_WALK_BASE_URL",
        VehicleType.BICYCLE: "OSRM_BICYCLE_BASE_URL",
        VehicleType.PUBLIC_TRANSPORT: "OSRM_PUBLIC_TRANSPORT_BASE_URL",
    }
    base_urls = {
        vehicle_type: os.getenv(variable_name, default_base_urls[vehicle_type])
        for vehicle_type, variable_name in environment_names.items()
    }
    default_profiles = {
        VehicleType.CAR: "driving",
        VehicleType.WALK: "walking" if has_common_profile_server else "driving",
        VehicleType.BICYCLE: "cycling" if has_common_profile_server else "driving",
        VehicleType.PUBLIC_TRANSPORT: "driving",
    }
    profile_names = {
        VehicleType.CAR: "OSRM_CAR_PROFILE",
        VehicleType.WALK: "OSRM_WALK_PROFILE",
        VehicleType.BICYCLE: "OSRM_BICYCLE_PROFILE",
        VehicleType.PUBLIC_TRANSPORT: "OSRM_PUBLIC_TRANSPORT_PROFILE",
    }
    profiles = {
        vehicle_type: os.getenv(variable_name, default_profiles[vehicle_type])
        for vehicle_type, variable_name in profile_names.items()
    }
    return OSRMRoutingProvider(
        coordinates=coordinates,
        request_timeout_seconds=request_timeout_seconds,
        max_rate_limit_retries=int(os.getenv("OSRM_MAX_RATE_LIMIT_RETRIES", "2")),
        rate_limit_backoff_seconds=float(
            os.getenv("OSRM_RATE_LIMIT_BACKOFF_SECONDS", "2")
        ),
        profiles=profiles,
        base_urls=base_urls,
    )

class RoutingProviderError(RuntimeError):
    """Ошибка получения матрицы или geometry от routing provider."""
