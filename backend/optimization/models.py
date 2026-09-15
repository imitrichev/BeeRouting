"""Предметные модели независимого Optimization Engine.

На границе domain-модели время задаётся как ``HH:MM``, длительности и время
движения — в минутах, расстояния — в километрах.
"""

from dataclasses import dataclass
from enum import Enum
import math
import re
from typing import Iterable, Mapping


class Skill(str, Enum):
    """Разрешённые навыки инженеров и заявок."""

    LOCAL_WORKS = "LOCAL_WORKS"
    CONNECTION_AND_UPSELL = "CONNECTION_AND_UPSELL"
    EMERGENCY_WORKS = "EMERGENCY_WORKS"


class VehicleType(str, Enum):
    """Разрешённые типы транспорта."""

    CAR = "CAR"
    WALK = "WALK"
    BICYCLE = "BICYCLE"
    PUBLIC_TRANSPORT = "PUBLIC_TRANSPORT"


class Priority(str, Enum):
    """Разрешённые приоритеты заявки."""

    NORMAL = "NORMAL"
    URGENT = "URGENT"


def hhmm_to_minutes(value: str) -> int:
    """Преобразует строку ``HH:MM`` в минуты от начала суток."""
    if not isinstance(value, str):
        raise ValueError("Время должно быть строкой в формате HH:MM")
    match = re.fullmatch(r"(\d+):([0-5]\d)", value.strip())
    if match is None:
        raise ValueError(f"Некорректное время {value!r}; ожидается формат HH:MM")
    return int(match.group(1)) * 60 + int(match.group(2))


def minutes_to_hhmm(minutes: int) -> str:
    """Преобразует целые минуты от начала суток в строку ``HH:MM``."""
    if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 0:
        raise ValueError("Количество минут должно быть целым и неотрицательным")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _enum_value(value: str | Enum, enum_type: type[Enum], field_name: str) -> Enum:
    """Преобразует строку или enum в значение заданного справочника."""
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        try:
            return enum_type(normalized)
        except ValueError as exc:
            allowed = ", ".join(member.value for member in enum_type)
            raise ValueError(
                f"{field_name} должен иметь одно из значений: {allowed}"
            ) from exc
    raise ValueError(f"{field_name} должен быть строкой или enum")


def _normalise_skills(values: Iterable[str | Skill]) -> frozenset[Skill]:
    """Преобразует набор навыков в значения фиксированного справочника."""
    return frozenset(_enum_value(value, Skill, "Навык") for value in values)


def _validate_coordinates(
    latitude: float | None,
    longitude: float | None,
) -> tuple[float | None, float | None]:
    """Проверяет парность и диапазоны координат широты и долготы."""
    if (latitude is None) != (longitude is None):
        raise ValueError("latitude и longitude должны задаваться вместе")
    if latitude is None:
        return None, None
    if not isinstance(latitude, (int, float)) or isinstance(latitude, bool):
        raise ValueError("latitude должна быть числом")
    if not isinstance(longitude, (int, float)) or isinstance(longitude, bool):
        raise ValueError("longitude должна быть числом")
    latitude_value = float(latitude)
    longitude_value = float(longitude)
    if not math.isfinite(latitude_value) or not -90 <= latitude_value <= 90:
        raise ValueError("latitude должна находиться в диапазоне [-90, 90]")
    if not math.isfinite(longitude_value) or not -180 <= longitude_value <= 180:
        raise ValueError("longitude должна находиться в диапазоне [-180, 180]")
    return latitude_value, longitude_value


@dataclass(frozen=True, slots=True)
class Engineer:
    """Инженер с одним типом транспорта и одним-тремя навыками."""

    id: str
    name: str
    qualifications: frozenset[Skill]
    start_location_id: str
    vehicle_type: VehicleType | str
    available_equipment: frozenset[str] = frozenset()
    equipment_resource_ids: frozenset[str] = frozenset()
    vehicle_resource_id: str | None = None
    start_latitude: float | None = None
    start_longitude: float | None = None

    def __post_init__(self) -> None:
        """Нормализует справочники и проверяет ограничения модели."""
        qualifications = _normalise_skills(self.qualifications)
        if not 1 <= len(qualifications) <= 3:
            raise ValueError("Инженер должен иметь от 1 до 3 навыков")
        latitude, longitude = _validate_coordinates(
            self.start_latitude, self.start_longitude
        )
        object.__setattr__(self, "qualifications", qualifications)
        object.__setattr__(self, "vehicle_type", _enum_value(
            self.vehicle_type, VehicleType, "vehicle_type"
        ))
        object.__setattr__(
            self,
            "available_equipment",
            frozenset(self.available_equipment),
        )
        object.__setattr__(
            self,
            "equipment_resource_ids",
            frozenset(self.equipment_resource_ids),
        )
        object.__setattr__(self, "start_latitude", latitude)
        object.__setattr__(self, "start_longitude", longitude)


@dataclass(frozen=True, slots=True)
class EquipmentResource:
    """Отдельный экземпляр оборудования ограниченного количества."""

    id: str
    equipment_type: str


@dataclass(frozen=True, slots=True)
class VehicleResource:
    """Отдельный экземпляр транспорта определённого типа."""

    id: str
    vehicle_type: VehicleType | str

    def __post_init__(self) -> None:
        """Проверяет тип транспорта по фиксированному справочнику."""
        object.__setattr__(self, "vehicle_type", _enum_value(
            self.vehicle_type, VehicleType, "vehicle_type"
        ))


@dataclass(frozen=True, slots=True)
class EngineerAvailability:
    """Рабочий интервал инженера в формате ``HH:MM``."""

    engineer_id: str
    available_from: str
    available_until: str

    def __post_init__(self) -> None:
        """Проверяет и нормализует границы рабочей смены."""
        available_from = minutes_to_hhmm(hhmm_to_minutes(self.available_from))
        available_until = minutes_to_hhmm(hhmm_to_minutes(self.available_until))
        if hhmm_to_minutes(available_until) <= hhmm_to_minutes(available_from):
            raise ValueError("available_until должен быть позже available_from")
        object.__setattr__(self, "available_from", available_from)
        object.__setattr__(self, "available_until", available_until)


@dataclass(frozen=True, slots=True)
class Task:
    """Заявка с одним навыком, длительностью и жёстким временным окном."""

    id: str
    location_id: str
    required_skills: frozenset[Skill]
    duration_minutes: int
    window_start: str
    window_end: str
    priority: Priority = Priority.NORMAL
    required_equipment: frozenset[str] = frozenset()
    required_vehicle_type: VehicleType | str | None = None
    latitude: float | None = None
    longitude: float | None = None

    def __post_init__(self) -> None:
        """Нормализует справочники и проверяет временное окно заявки."""
        skills = _normalise_skills(self.required_skills)
        if len(skills) != 1:
            raise ValueError("Заявка должна требовать ровно один навык")
        if isinstance(self.duration_minutes, bool) or not isinstance(
            self.duration_minutes, int
        ) or self.duration_minutes < 0:
            raise ValueError("duration_minutes должен быть целым и неотрицательным")
        window_start = minutes_to_hhmm(hhmm_to_minutes(self.window_start))
        window_end = minutes_to_hhmm(hhmm_to_minutes(self.window_end))
        if hhmm_to_minutes(window_end) <= hhmm_to_minutes(window_start):
            raise ValueError("window_end должен быть позже window_start")
        latitude, longitude = _validate_coordinates(self.latitude, self.longitude)
        vehicle_type = (
            None
            if self.required_vehicle_type is None
            else _enum_value(self.required_vehicle_type, VehicleType, "required_vehicle_type")
        )
        object.__setattr__(self, "required_skills", skills)
        object.__setattr__(self, "window_start", window_start)
        object.__setattr__(self, "window_end", window_end)
        object.__setattr__(self, "priority", _enum_value(self.priority, Priority, "priority"))
        object.__setattr__(self, "required_equipment", frozenset(self.required_equipment))
        object.__setattr__(self, "required_vehicle_type", vehicle_type)
        object.__setattr__(self, "latitude", latitude)
        object.__setattr__(self, "longitude", longitude)


@dataclass(frozen=True, slots=True)
class OptimizationProblem:
    """Входные данные маршрутизации и внешние матрицы.

    ``travel_time_matrix`` содержит целые минуты, а
    ``travel_distance_matrix`` — километры. Обе матрицы обязательны и должны
    описывать один и тот же набор локаций.
    """

    engineers: tuple[Engineer, ...]
    availabilities: tuple[EngineerAvailability, ...]
    tasks: tuple[Task, ...]
    travel_time_matrix: Mapping[str, Mapping[str, int]]
    travel_distance_matrix: Mapping[str, Mapping[str, float]]
    equipment_resources: tuple[EquipmentResource, ...] = ()
    vehicle_resources: tuple[VehicleResource, ...] = ()

    def __post_init__(self) -> None:
        """Проверяет идентификаторы, ресурсы и полноту внешних матриц."""
        engineers = tuple(self.engineers)
        availabilities = tuple(self.availabilities)
        tasks = tuple(self.tasks)
        equipment_resources = tuple(self.equipment_resources)
        vehicle_resources = tuple(self.vehicle_resources)
        matrix = {
            source: dict(destinations)
            for source, destinations in self.travel_time_matrix.items()
        }
        distance_matrix = {
            source: dict(destinations)
            for source, destinations in self.travel_distance_matrix.items()
        }
        object.__setattr__(self, "engineers", engineers)
        object.__setattr__(self, "availabilities", availabilities)
        object.__setattr__(self, "tasks", tasks)
        object.__setattr__(self, "equipment_resources", equipment_resources)
        object.__setattr__(self, "vehicle_resources", vehicle_resources)
        object.__setattr__(self, "travel_time_matrix", matrix)
        object.__setattr__(self, "travel_distance_matrix", distance_matrix)

        if not engineers:
            raise ValueError("В задаче должен быть хотя бы один инженер")
        if not tasks:
            raise ValueError("В задаче должна быть хотя бы одна заявка")
        engineer_ids = [engineer.id for engineer in engineers]
        task_ids = [task.id for task in tasks]
        availability_ids = [availability.engineer_id for availability in availabilities]
        if len(engineer_ids) != len(set(engineer_ids)):
            raise ValueError("Идентификаторы инженеров должны быть уникальными")
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Идентификаторы заявок должны быть уникальными")
        if len(availability_ids) != len(set(availability_ids)):
            raise ValueError("Доступность должна быть задана один раз для каждого инженера")
        if set(availability_ids) != set(engineer_ids):
            raise ValueError("Должна быть задана доступность каждого инженера и только их")

        equipment_ids = [resource.id for resource in equipment_resources]
        vehicle_ids = [resource.id for resource in vehicle_resources]
        if len(equipment_ids) != len(set(equipment_ids)):
            raise ValueError("Идентификаторы оборудования должны быть уникальными")
        if len(vehicle_ids) != len(set(vehicle_ids)):
            raise ValueError("Идентификаторы транспорта должны быть уникальными")
        equipment_by_id = {resource.id: resource for resource in equipment_resources}
        vehicle_by_id = {resource.id: resource for resource in vehicle_resources}
        for engineer in engineers:
            missing_equipment = engineer.equipment_resource_ids - equipment_by_id.keys()
            if missing_equipment:
                raise ValueError(
                    f"У инженера {engineer.id} есть неизвестное оборудование: "
                    f"{sorted(missing_equipment)}"
                )
            if engineer.vehicle_resource_id is not None:
                if engineer.vehicle_resource_id not in vehicle_by_id:
                    raise ValueError(
                        f"У инженера {engineer.id} указан неизвестный транспорт: "
                        f"{engineer.vehicle_resource_id}"
                    )
                if engineer.vehicle_type != vehicle_by_id[engineer.vehicle_resource_id].vehicle_type:
                    raise ValueError(
                        f"Тип транспорта инженера {engineer.id} не совпадает "
                        "с типом закреплённого экземпляра"
                    )

        location_ids = {
            engineer.start_location_id for engineer in engineers
        } | {task.location_id for task in tasks}
        self._validate_matrix(matrix, location_ids, "Время движения", integer=True)
        self._validate_matrix(distance_matrix, location_ids, "Расстояние", integer=False)

    @staticmethod
    def _validate_matrix(
        matrix: Mapping[str, Mapping[str, int | float]],
        location_ids: set[str],
        label: str,
        integer: bool,
    ) -> None:
        """Проверяет полную матрицу времени или расстояний."""
        missing_origins = location_ids - matrix.keys()
        if missing_origins:
            raise ValueError(f"{label}: отсутствуют исходные локации: {sorted(missing_origins)}")
        for source in location_ids:
            missing_destinations = location_ids - matrix[source].keys()
            if missing_destinations:
                raise ValueError(
                    f"{label}: в строке {source} отсутствуют локации: "
                    f"{sorted(missing_destinations)}"
                )
            for value in matrix[source].values():
                valid = (
                    isinstance(value, int) and not isinstance(value, bool)
                    if integer
                    else isinstance(value, (int, float)) and not isinstance(value, bool)
                )
                if not valid or value < 0 or not math.isfinite(float(value)):
                    units = "целым числом минут" if integer else "числом километров"
                    raise ValueError(f"{label} должно быть неотрицательным {units}")


@dataclass(frozen=True, slots=True)
class RouteStop:
    """Результат посещения заявки; времена представлены как ``HH:MM``."""

    task_id: str
    arrival_time: str
    service_start_time: str
    service_end_time: str
    travel_time_from_previous: int
    distance_from_previous_km: float = 0.0


@dataclass(frozen=True, slots=True)
class EngineerRoute:
    """Упорядоченный маршрут инженера в доменных единицах."""

    engineer_id: str
    stops: tuple[RouteStop, ...]
    total_travel_minutes: int
    total_service_minutes: int
    total_distance_km: float = 0.0


class UnassignedReasonCode(str, Enum):
    """Коды причин, по которым заявка не попала в маршруты."""

    MISSING_QUALIFICATION = "missing_qualification"
    MISSING_EQUIPMENT = "missing_equipment"
    MISSING_VEHICLE_TYPE = "missing_vehicle_type"
    IMPOSSIBLE_TIME_WINDOW = "impossible_time_window"
    OUTSIDE_WORKING_HOURS = "outside_working_hours"


@dataclass(frozen=True, slots=True)
class UnassignedReason:
    """Структурированное объяснение неназначения заявки."""

    code: UnassignedReasonCode
    message: str


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Маршруты, неназначенные заявки и разложение целевой функции."""

    routes: Mapping[str, EngineerRoute]
    unassigned_task_ids: tuple[str, ...]
    unassigned_reasons: Mapping[str, UnassignedReason]
    distance_by_engineer: Mapping[str, float]
    total_distance: float
    travel_time_by_engineer: Mapping[str, int]
    total_travel_time: int
    used_engineers_count: int
    assigned_task_count: int
    unassigned_task_count: int
    total_objective: int
    total_service_minutes: int = 0
    unassigned_penalty: int = 0
    used_engineers_penalty: int = 0
    distance_penalty: int = 0
    travel_time_penalty: int = 0

    def __post_init__(self) -> None:
        """Проверяет метрики маршрутов и сумму компонентов objective."""
        penalty_sum = (
            self.unassigned_penalty
            + self.used_engineers_penalty
            + self.distance_penalty
            + self.travel_time_penalty
        )
        if self.total_objective != penalty_sum:
            raise ValueError(
                "total_objective должен быть равен сумме компонентов objective"
            )
        if set(self.unassigned_reasons) != set(self.unassigned_task_ids):
            raise ValueError("Для каждой неназначенной заявки должна быть задана одна причина")
        if set(self.distance_by_engineer) != set(self.routes):
            raise ValueError("Пробег должен быть указан для каждого инженера")
        if set(self.travel_time_by_engineer) != set(self.routes):
            raise ValueError("Время движения должно быть указано для каждого инженера")
        if self.assigned_task_count != sum(
            len(route.stops) for route in self.routes.values()
        ):
            raise ValueError("assigned_task_count не соответствует маршрутам")
        if self.unassigned_task_count != len(self.unassigned_task_ids):
            raise ValueError("unassigned_task_count не соответствует заявкам")
        if self.used_engineers_count != sum(
            bool(route.stops) for route in self.routes.values()
        ):
            raise ValueError("used_engineers_count не соответствует маршрутам")
        if not math.isclose(
            self.total_distance,
            math.fsum(self.distance_by_engineer.values()),
        ):
            raise ValueError("total_distance не соответствует пробегу инженеров")
        if self.total_travel_time != sum(self.travel_time_by_engineer.values()):
            raise ValueError("total_travel_time не соответствует времени инженеров")
