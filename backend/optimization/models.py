"""Предметные модели независимого Optimization Engine.

На границе domain-модели время задаётся как ``HH:MM``, длительности и время
движения — в минутах, расстояния — в километрах.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from typing import Iterable, Mapping


class Skill(str, Enum):
    """Фиксированный справочник квалификаций инженеров и типов работ."""

    LOCAL_WORKS = "LOCAL_WORKS"  # Локальные монтажные и ремонтные работы.
    CONNECTION_AND_UPSELL = "CONNECTION_AND_UPSELL"  # Подключение и продажа услуг.
    EMERGENCY_WORKS = "EMERGENCY_WORKS"  # Аварийные работы.


class VehicleType(str, Enum):
    """Разрешённые типы транспорта."""

    CAR = "CAR"  # Личный или служебный автомобиль.
    WALK = "WALK"  # Передвижение пешком.
    BICYCLE = "BICYCLE"  # Велосипед.
    PUBLIC_TRANSPORT = "PUBLIC_TRANSPORT"  # Общественный транспорт.


class Priority(str, Enum):
    """Разрешённые приоритеты заявки."""

    NORMAL = "NORMAL"  # Обычный приоритет.
    URGENT = "URGENT"  # Срочная заявка; её неназначение дороже.


class TaskStatus(str, Enum):
    """Статусы заявки, которые приходят из исходных данных и API.

    ``OVERDUE`` пока только хранит уже зафиксированный статус из источника.
    Автоматическое определение просрочки по текущему времени появится позже
    во frontend/backend-сценарии диспетчера.
    """

    NOT_SENT = "NOT_SENT"  # Заявка ещё не назначена инженеру.
    ASSIGNED = "ASSIGNED"  # Заявка назначена инженеру, но работа ещё не начата.
    EN_ROUTE = "EN_ROUTE"  # Инженер направляется к месту выполнения заявки.
    IN_PROGRESS = "IN_PROGRESS"  # Инженер уже выполняет работу на объекте.
    COMPLETED = "COMPLETED"  # Работа по заявке завершена.
    CANCELLED = "CANCELLED"  # Заявка отменена и не должна занимать время маршрута.
    OVERDUE = "OVERDUE"  # Заявка не была начата в установленный срок.


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


def _normalise_skills(values: Iterable[Skill]) -> frozenset[Skill]:
    """Проверяет набор квалификаций, уже преобразованных в ``Skill``."""
    skills = frozenset(values)
    if any(not isinstance(skill, Skill) for skill in skills):
        allowed = ", ".join(skill.value for skill in Skill)
        raise ValueError(f"Квалификации должны быть значениями Skill: {allowed}")
    return skills


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

    id: str  # Уникальный идентификатор инженера.
    name: str  # Отображаемое имя инженера.
    qualifications: frozenset[Skill]  # Навыки, которыми владеет инженер.
    start_location_id: str  # Локация, откуда начинается его маршрут.
    vehicle_type: VehicleType  # Единственный тип транспорта из фиксированного справочника.
    available_equipment: frozenset[str] = frozenset()  # Оборудование, доступное инженеру постоянно.
    equipment_resource_ids: frozenset[str] = frozenset()  # ID отдельных экземпляров оборудования из problem.
    vehicle_resource_id: str | None = None  # ID закреплённого экземпляра транспорта, если он моделируется.
    start_latitude: float | None = None  # Широта стартовой точки в градусах WGS84.
    start_longitude: float | None = None  # Долгота стартовой точки в градусах WGS84.

    def __post_init__(self) -> None:
        """Нормализует справочники и проверяет ограничения модели."""
        qualifications = _normalise_skills(self.qualifications)
        if not 1 <= len(qualifications) <= 3:
            raise ValueError("Инженер должен иметь от 1 до 3 навыков")
        latitude, longitude = _validate_coordinates(
            self.start_latitude, self.start_longitude
        )
        object.__setattr__(self, "qualifications", qualifications)
        if not isinstance(self.vehicle_type, VehicleType):
            raise ValueError("vehicle_type должен быть значением VehicleType")
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

    id: str  # Уникальный идентификатор конкретного экземпляра.
    equipment_type: str  # Вид оборудования, например "multimeter".


@dataclass(frozen=True, slots=True)
class VehicleResource:
    """Отдельный экземпляр транспорта определённого типа."""

    id: str  # Уникальный идентификатор конкретного транспортного средства.
    vehicle_type: VehicleType  # Тип транспорта из фиксированного справочника.

    def __post_init__(self) -> None:
        """Проверяет тип транспорта по фиксированному справочнику."""
        if not isinstance(self.vehicle_type, VehicleType):
            raise ValueError("vehicle_type должен быть значением VehicleType")


@dataclass(frozen=True, slots=True)
class EngineerAvailability:
    """Рабочий интервал инженера в формате ``HH:MM``."""

    engineer_id: str  # ID инженера, к которому относится рабочий интервал.
    available_from: str  # Начало смены в формате HH:MM.
    available_until: str  # Конец смены в формате HH:MM; работа должна завершиться до него.

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
    """Заявка с требуемой квалификацией, длительностью и жёстким окном.

    ``required_skills`` описывает квалификацию инженера, необходимую для
    выполнения типа работ по заявке, а не отдельный навык самой заявки.
    """

    id: str  # Уникальный идентификатор заявки.
    location_id: str  # Локация, которую нужно посетить.
    required_skills: frozenset[Skill]  # Ровно одна требуемая квалификация инженера для типа работ.
    duration_minutes: int  # Продолжительность обслуживания в целых минутах.
    window_start: str  # Самое раннее допустимое начало работы, HH:MM.
    window_end: str  # Самое позднее допустимое начало работы, HH:MM.
    priority: Priority = Priority.NORMAL  # Приоритет для штрафа неназначения.
    status: TaskStatus = TaskStatus.NOT_SENT  # Текущий статус; отменённая заявка не занимает маршрутное время.
    required_equipment: frozenset[str] = frozenset()  # Всё оборудование, необходимое на заявке.
    required_vehicle_type: VehicleType | None = None  # Требуемый тип транспорта или отсутствие требования.
    latitude: float | None = None  # Широта точки заявки в градусах WGS84.
    longitude: float | None = None  # Долгота точки заявки в градусах WGS84.

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
        if self.required_vehicle_type is not None and not isinstance(
            self.required_vehicle_type, VehicleType
        ):
            raise ValueError(
                "required_vehicle_type должен быть значением VehicleType или None"
            )
        object.__setattr__(self, "required_skills", skills)
        object.__setattr__(self, "window_start", window_start)
        object.__setattr__(self, "window_end", window_end)
        if not isinstance(self.priority, Priority):
            raise ValueError("priority должен быть значением Priority")
        if not isinstance(self.status, TaskStatus):
            raise ValueError("status должен быть значением TaskStatus")
        object.__setattr__(self, "required_equipment", frozenset(self.required_equipment))
        object.__setattr__(self, "latitude", latitude)
        object.__setattr__(self, "longitude", longitude)


@dataclass(frozen=True, slots=True)
class OptimizationProblem:
    """Входные данные маршрутизации и внешние матрицы.

    ``travel_time_matrix`` содержит целые минуты, а
    ``travel_distance_matrix`` — километры. Обе матрицы обязательны и должны
    описывать один и тот же набор локаций.
    """

    engineers: tuple[Engineer, ...]  # Все инженеры, между которыми выбирается назначение.
    availabilities: tuple[EngineerAvailability, ...]  # Рабочее время каждого инженера.
    tasks: tuple[Task, ...]  # Заявки в порядке их поступления.
    travel_time_matrix: Mapping[str, Mapping[str, int]]  # [откуда][куда]: время движения в минутах.
    travel_distance_matrix: Mapping[str, Mapping[str, float]]  # [откуда][куда]: расстояние в километрах.
    travel_time_matrices_by_vehicle: Mapping[
        VehicleType, Mapping[str, Mapping[str, int]]
    ] = field(default_factory=dict)  # Необязательные матрицы времени по профилям транспорта.
    travel_distance_matrices_by_vehicle: Mapping[
        VehicleType, Mapping[str, Mapping[str, float]]
    ] = field(default_factory=dict)  # Необязательные матрицы расстояний по профилям транспорта.
    equipment_resources: tuple[EquipmentResource, ...] = ()  # Необязательные отдельные экземпляры оборудования.
    vehicle_resources: tuple[VehicleResource, ...] = ()  # Необязательные отдельные экземпляры транспорта.

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
        time_matrices_by_vehicle = {
            vehicle_type: {
                source: dict(destinations)
                for source, destinations in matrix.items()
            }
            for vehicle_type, matrix in self.travel_time_matrices_by_vehicle.items()
        }
        distance_matrices_by_vehicle = {
            vehicle_type: {
                source: dict(destinations)
                for source, destinations in matrix.items()
            }
            for vehicle_type, matrix in self.travel_distance_matrices_by_vehicle.items()
        }
        object.__setattr__(self, "engineers", engineers)
        object.__setattr__(self, "availabilities", availabilities)
        object.__setattr__(self, "tasks", tasks)
        object.__setattr__(self, "equipment_resources", equipment_resources)
        object.__setattr__(self, "vehicle_resources", vehicle_resources)
        object.__setattr__(self, "travel_time_matrix", matrix)
        object.__setattr__(self, "travel_distance_matrix", distance_matrix)
        object.__setattr__(self, "travel_time_matrices_by_vehicle", time_matrices_by_vehicle)
        object.__setattr__(self, "travel_distance_matrices_by_vehicle", distance_matrices_by_vehicle)

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
        for vehicle_type, vehicle_matrix in time_matrices_by_vehicle.items():
            if not isinstance(vehicle_type, VehicleType):
                raise ValueError("Ключ матрицы времени должен быть значением VehicleType")
            self._validate_matrix(
                vehicle_matrix,
                location_ids,
                f"Время движения для {vehicle_type.value}",
                integer=True,
            )
        for vehicle_type, vehicle_matrix in distance_matrices_by_vehicle.items():
            if not isinstance(vehicle_type, VehicleType):
                raise ValueError("Ключ матрицы расстояний должен быть значением VehicleType")
            self._validate_matrix(
                vehicle_matrix,
                location_ids,
                f"Расстояние для {vehicle_type.value}",
                integer=False,
            )
        if set(time_matrices_by_vehicle) != set(distance_matrices_by_vehicle):
            raise ValueError("Для каждого транспортного профиля нужны обе матрицы")

    def travel_time_between(
        self,
        from_location: str,
        to_location: str,
        vehicle_type: VehicleType,
    ) -> int:
        """Возвращает время движения из матрицы профиля инженера."""
        matrix = self.travel_time_matrices_by_vehicle.get(
            vehicle_type, self.travel_time_matrix
        )
        return matrix[from_location][to_location]

    def travel_distance_between(
        self,
        from_location: str,
        to_location: str,
        vehicle_type: VehicleType,
    ) -> float:
        """Возвращает расстояние из матрицы профиля инженера."""
        matrix = self.travel_distance_matrices_by_vehicle.get(
            vehicle_type, self.travel_distance_matrix
        )
        return float(matrix[from_location][to_location])

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

    task_id: str  # ID обслуженной заявки.
    arrival_time: str  # Фактическое прибытие на локацию, HH:MM.
    service_start_time: str  # Фактическое начало работы, HH:MM.
    service_end_time: str  # Окончание работы, HH:MM.
    travel_time_from_previous: int  # Время движения от базы или предыдущей заявки, минуты.
    distance_from_previous_km: float = 0.0  # Расстояние от базы или предыдущей заявки, километры.


@dataclass(frozen=True, slots=True)
class EngineerRoute:
    """Упорядоченный маршрут инженера в доменных единицах."""

    engineer_id: str  # ID инженера-владельца маршрута.
    stops: tuple[RouteStop, ...]  # Заявки в фактическом порядке посещения.
    total_travel_minutes: int  # Суммарное время движения по маршруту, минуты.
    total_service_minutes: int  # Суммарное время обслуживания, минуты.
    total_distance_km: float = 0.0  # Суммарное расстояние маршрута, километры.


class UnassignedReasonCode(str, Enum):
    """Коды причин, по которым заявка не попала в маршруты."""

    MISSING_QUALIFICATION = "missing_qualification"  # Нет подходящего навыка.
    MISSING_EQUIPMENT = "missing_equipment"  # Не хватает хотя бы одного устройства.
    MISSING_VEHICLE_TYPE = "missing_vehicle_type"  # Нет подходящего типа транспорта.
    IMPOSSIBLE_TIME_WINDOW = "impossible_time_window"  # Нельзя начать работу в окне.
    OUTSIDE_WORKING_HOURS = "outside_working_hours"  # Работа не помещается в смену.
    RESOURCE_CONFLICT = "resource_conflict"  # Один экземпляр ресурса уже занят.


@dataclass(frozen=True, slots=True)
class UnassignedReason:
    """Структурированное объяснение неназначения заявки."""

    code: UnassignedReasonCode  # Машиночитаемый код причины.
    message: str  # Пояснение для пользователя или последующего XAI-слоя.


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Маршруты, неназначенные заявки и разложение целевой функции."""

    routes: Mapping[str, EngineerRoute]  # Маршрут каждого инженера, включая пустые маршруты.
    unassigned_task_ids: tuple[str, ...]  # ID заявок, которым не нашлось допустимого места.
    unassigned_reasons: Mapping[str, UnassignedReason]  # Причина для каждого ID из unassigned_task_ids.
    distance_by_engineer: Mapping[str, float]  # Пробег каждого инженера, километры.
    total_distance: float  # Суммарный пробег всех маршрутов, километры.
    travel_time_by_engineer: Mapping[str, int]  # Время движения каждого инженера, минуты.
    total_travel_time: int  # Суммарное время движения всех маршрутов, минуты.
    used_engineers_count: int  # Число инженеров, у которых есть хотя бы одна заявка.
    assigned_task_count: int  # Число заявок во всех непустых маршрутах.
    unassigned_task_count: int  # Число заявок без маршрута.
    total_objective: int  # Итоговая стоимость по четырём компонентам ниже.
    total_service_minutes: int = 0  # Суммарная длительность обслуживания, минуты.
    unassigned_penalty: int = 0  # Штраф за неназначенные заявки с учётом приоритета.
    used_engineers_penalty: int = 0  # Штраф за количество задействованных инженеров.
    distance_penalty: int = 0  # Взвешенный штраф за общий пробег.
    travel_time_penalty: int = 0  # Взвешенный штраф за общее время движения.

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
