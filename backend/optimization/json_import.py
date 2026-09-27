"""Импорт сценария Optimization Engine из JSON-файла.

Импортёр преобразует формат ``Югоцентр.json`` в domain-модели. Матрицы
маршрутизации в файл не входят, поэтому их должен передать вызывающий код
через ``RoutingProvider``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import (
    Engineer,
    EngineerAvailability,
    EngineerOperationalState,
    OptimizationProblem,
    Priority,
    Skill,
    Task,
    TaskStatus,
    VehicleType,
    WorkType,
)
from .routing_provider import RoutingProvider


# JSON использует более короткие коды, чем внутренний фиксированный справочник.
# Все преобразования собраны здесь, чтобы solver работал только с enum-моделями.
_SKILL_CODES = {
    "local_works": Skill.LOCAL_WORKS,
    "connection_orders": Skill.CONNECTION_AND_UPSELL,
    "emergency_works": Skill.EMERGENCY_WORKS,
}
_VEHICLE_CODES = {
    "car": VehicleType.CAR,
    "foot": VehicleType.WALK,
    "bicycle": VehicleType.BICYCLE,
    "public_transport": VehicleType.PUBLIC_TRANSPORT,
}
_PRIORITY_CODES = {
    "normal": Priority.NORMAL,
    "urgent": Priority.URGENT,
}
_STATUS_CODES = {
    "не отправлена": TaskStatus.NOT_SENT,
    "отправлена": TaskStatus.ASSIGNED,
    "назначена": TaskStatus.ASSIGNED,
    "в пути": TaskStatus.EN_ROUTE,
    "в работе": TaskStatus.IN_PROGRESS,
    "выполнена": TaskStatus.COMPLETED,
    "отменена": TaskStatus.CANCELLED,
    "просрочена": TaskStatus.OVERDUE,
}
_WORK_TYPE_CODES = {
    "connection": WorkType.CONNECTION,
    "emergency": WorkType.EMERGENCY,
    "equipment_order": WorkType.EQUIPMENT_ORDER,
    "local": WorkType.LOCAL,
}


def _work_type(job: Mapping[str, Any]) -> WorkType:
    """Определяет тип работ из норматива, сохраняя старые JSON без этого поля."""
    code = str(job.get("time_norm_code", "")).strip().lower()
    if code in _WORK_TYPE_CODES:
        return _WORK_TYPE_CODES[code]
    skill_code = str(job.get("skill_required", "")).strip().lower()
    if skill_code == "emergency_works":
        return WorkType.EMERGENCY
    if skill_code == "local_works":
        return WorkType.LOCAL
    # Подключение и дозаказ используют один навык. В старом формате их
    # различает официальный норматив работы после прибытия: 70 и 20 минут.
    return (
        WorkType.EQUIPMENT_ORDER
        if job.get("duration_min") == 20
        else WorkType.CONNECTION
    )


@dataclass(frozen=True, slots=True)
class JsonScenario:
    """Загруженная из JSON часть задачи без матриц маршрутизации."""

    scenario_name: str  # Название сценария из JSON, например yugo_tsentr_day.
    engineers: tuple[Engineer, ...]  # Инженеры с навыками, транспортом и координатами базы.
    availabilities: tuple[EngineerAvailability, ...]  # Рабочие смены инженеров.
    tasks: tuple[Task, ...]  # Заявки в том же порядке, в котором они записаны в JSON.
    location_coordinates: dict[str, tuple[float, float]]  # Координаты каждой локации: latitude, longitude.
    office_address: str | None = None  # Человекочитаемый адрес общей стартовой точки.
    office_latitude: float | None = None  # Широта офиса для отдельного маркера карты.
    office_longitude: float | None = None  # Долгота офиса для отдельного маркера карты.
    reference_engineer_by_task: dict[str, str] = field(default_factory=dict)  # Ручной исполнитель из исходного JSON, если он указан.
    reference_status_by_task: dict[str, TaskStatus] = field(default_factory=dict)  # Исходный статус заявки для контрольного плана.
    reference_sequence_by_task: dict[str, int] = field(default_factory=dict)  # Порядок строки контрольного плана, начиная с 1.
    control_request_id_by_task: dict[str, str] = field(default_factory=dict)  # Номер заявки из контрольного CSV, если он отличается от синтетического номера.

    def to_problem(
        self,
        routing_provider: RoutingProvider,
        vehicle_types: Iterable[VehicleType] | None = None,
        preserve_assigned_tasks: bool = False,
        ignore_task_statuses: bool = False,
        planning_time: str | None = None,
        operational_states: Iterable[EngineerOperationalState] = (),
        unavailable_engineer_ids: Iterable[str] = (),
        consider_equipment: bool = False,
    ) -> OptimizationProblem:
        """Добавляет внешние матрицы и создаёт ``OptimizationProblem``.

        Один и тот же набор локаций передаётся provider для времени и
        расстояния. Это гарантирует, что две матрицы имеют одинаковые строки
        и столбцы и могут безопасно использоваться одним solver.
        """
        location_ids = tuple(
            dict.fromkeys(
                [engineer.start_location_id for engineer in self.engineers]
                + [task.location_id for task in self.tasks]
                + [state.current_location_id for state in operational_states]
            )
        )
        # Если вызывающий код не передал профили явно, запрашиваем все типы,
        # которые реально есть у инженеров. Иначе problem получил бы только
        # базовую матрицу CAR, а время общественного транспорта, велосипеда
        # и пешего маршрута не участвовало бы в проверке смен и окон.
        requested_vehicle_types = tuple(
            dict.fromkeys(
                vehicle_types
                if vehicle_types is not None
                else (engineer.vehicle_type for engineer in self.engineers)
            )
        )
        time_matrices_by_vehicle = {
            vehicle_type: routing_provider.get_travel_time_matrix(
                location_ids, vehicle_type
            )
            for vehicle_type in requested_vehicle_types
        }
        distance_matrices_by_vehicle = {
            vehicle_type: routing_provider.get_distance_matrix(
                location_ids, vehicle_type
            )
            for vehicle_type in requested_vehicle_types
        }
        base_vehicle_type = (
            VehicleType.CAR
            if VehicleType.CAR in requested_vehicle_types
            else requested_vehicle_types[0]
            if requested_vehicle_types
            else None
        )
        return OptimizationProblem(
            engineers=self.engineers,
            availabilities=self.availabilities,
            tasks=self.tasks,
            travel_time_matrix=(
                time_matrices_by_vehicle[base_vehicle_type]
                if base_vehicle_type is not None
                else routing_provider.get_travel_time_matrix(location_ids)
            ),
            travel_distance_matrix=(
                distance_matrices_by_vehicle[base_vehicle_type]
                if base_vehicle_type is not None
                else routing_provider.get_distance_matrix(location_ids)
            ),
            travel_time_matrices_by_vehicle=time_matrices_by_vehicle,
            travel_distance_matrices_by_vehicle=distance_matrices_by_vehicle,
            preserve_assigned_tasks=preserve_assigned_tasks,
            ignore_task_statuses=ignore_task_statuses,
            planning_time=planning_time,
            operational_states=tuple(operational_states),
            unavailable_engineer_ids=frozenset(unavailable_engineer_ids),
            consider_equipment=consider_equipment,
        )


def load_json_scenario(path: str | Path) -> JsonScenario:
    """Загружает и валидирует поддерживаемый JSON-сценарий."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return load_json_scenario_data(payload)


def load_json_scenario_data(payload: Mapping[str, Any]) -> JsonScenario:
    """Преобразует уже разобранный JSON-объект в ``JsonScenario``.

    Функция нужна API загрузки: Django передаёт содержимое multipart-файла
    напрямую, не добавляя файловое хранилище в математическое ядро.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("Корень JSON-сценария должен быть объектом")
    payload = dict(payload)

    office = _mapping(payload, "office_start_point")
    office_coordinates = _coordinates(office, "lat", "lon")
    office_address = str(office.get("address") or "").strip() or None
    office_location_id = "office_start"
    location_coordinates: dict[str, tuple[float, float]] = {
        office_location_id: office_coordinates
    }

    engineers_data = _list(payload, "engineers")
    engineers: list[Engineer] = []
    availabilities: list[EngineerAvailability] = []
    for item in engineers_data:
        engineer_data = _mapping_value(item, "engineer")
        engineer_id = _string(engineer_data, "engineer_id")
        start_lat, start_lon = _coordinates(engineer_data, "start_lat", "start_lon")
        # Старт — свойство инженера, а не офиса. Отдельный ID не позволяет
        # матрице маршрутизации слить разные домашние/полевые точки в один узел.
        start_location_id = f"engineer_start:{engineer_id}"
        location_coordinates[start_location_id] = (start_lat, start_lon)
        engineers.append(
            Engineer(
                id=engineer_id,
                name=_string(engineer_data, "name"),
                qualifications=frozenset(
                    _mapped_value(code, _SKILL_CODES, "skill")
                    for code in _list(engineer_data, "skills")
                ),
                start_location_id=start_location_id,
                vehicle_type=_mapped_value(
                    _string(engineer_data, "vehicle_type"),
                    _VEHICLE_CODES,
                    "vehicle_type",
                ),
                start_latitude=start_lat,
                start_longitude=start_lon,
                available_router_count=int(
                    engineer_data.get("available_router_count", 0)
                ),
            )
        )
        availabilities.append(
            EngineerAvailability(
                engineer_id=engineer_id,
                available_from=_string(engineer_data, "shift_start"),
                available_until=_string(engineer_data, "shift_end"),
            )
        )

    engineer_id_by_name = {engineer.name: engineer.id for engineer in engineers}

    tasks: list[Task] = []
    reference_engineer_by_task: dict[str, str] = {}
    reference_status_by_task: dict[str, TaskStatus] = {}
    reference_sequence_by_task: dict[str, int] = {}
    control_request_id_by_task: dict[str, str] = {}
    for item in _list(payload, "jobs"):
        job = _mapping_value(item, "job")
        task_id = _string(job, "job_id")
        task_lat, task_lon = _coordinates(job, "lat", "lon")
        location_coordinates[task_id] = (task_lat, task_lon)
        required_vehicle = job.get("required_vehicle")
        reference_crew = job.get("reference_crew", "")
        if not isinstance(reference_crew, str):
            raise ValueError("Поле 'reference_crew' должно быть строкой")
        reference_crew = reference_crew.strip()
        current_engineer_id = None
        if reference_crew:
            current_engineer_id = engineer_id_by_name.get(reference_crew)
            # Контрольные файлы других районов могут ссылаться на бригады,
            # которых ещё нет в переданном справочнике engineers. Сам JSON при
            # этом остаётся доступен для просмотра; построение problem выдаст
            # отдельную ошибку только если неизвестного инженера требуется
            # зафиксировать для EN_ROUTE/IN_PROGRESS.
        tasks.append(
            Task(
                id=task_id,
                location_id=task_id,
                required_skills=frozenset(
                    {
                        _mapped_value(
                            _string(job, "skill_required"),
                            _SKILL_CODES,
                            "skill_required",
                        )
                    }
                ),
                duration_minutes=_integer(job, "duration_min"),
                window_start=_string(job, "window_start"),
                window_end=_string(job, "window_end"),
                work_type=_work_type(job),
                priority=_mapped_value(
                    _string(job, "priority"), _PRIORITY_CODES, "priority"
                ),
                status=_mapped_value(
                    _string(job, "reference_status").lower(),
                    _STATUS_CODES,
                    "reference_status",
                ),
                current_engineer_id=current_engineer_id,
                required_vehicle_type=(
                    None
                    if required_vehicle is None
                    else _mapped_value(
                        _string_value(required_vehicle, "required_vehicle"),
                        _VEHICLE_CODES,
                        "required_vehicle",
                    )
                ),
                latitude=task_lat,
                longitude=task_lon,
                address=str(job.get("address", "")).strip() or None,
                required_router_count=int(job.get("required_router_count", 0)),
            )
        )
        # У неназначенной заявки (`Не отправлена`) исполнителя ещё нет.
        # Пустое значение сохраняем как пустую строку; для назначенных заявок
        # контрольный план по-прежнему проверит имя инженера отдельно.
        reference_engineer_by_task[task_id] = reference_crew
        reference_status_by_task[task_id] = tasks[-1].status
        reference_sequence = job.get("reference_sequence")
        if reference_sequence is not None:
            if isinstance(reference_sequence, bool) or not isinstance(reference_sequence, int):
                raise ValueError("Поле 'reference_sequence' должно быть целым числом")
            if reference_sequence <= 0:
                raise ValueError("Поле 'reference_sequence' должно быть положительным")
            reference_sequence_by_task[task_id] = reference_sequence
        if job.get("control_request_id") is not None:
            control_request_id_by_task[task_id] = str(job["control_request_id"])

    return JsonScenario(
        scenario_name=_string(payload, "scenario"),
        engineers=tuple(engineers),
        availabilities=tuple(availabilities),
        tasks=tuple(tasks),
        location_coordinates=location_coordinates,
        office_address=office_address,
        office_latitude=office_coordinates[0],
        office_longitude=office_coordinates[1],
        reference_engineer_by_task=reference_engineer_by_task,
        reference_status_by_task=reference_status_by_task,
        reference_sequence_by_task=reference_sequence_by_task,
        control_request_id_by_task=control_request_id_by_task,
    )


def load_problem_from_json(
    path: str | Path,
    routing_provider: RoutingProvider,
) -> OptimizationProblem:
    """Загружает JSON и сразу собирает ``OptimizationProblem`` через provider."""
    return load_json_scenario(path).to_problem(routing_provider)


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Возвращает обязательное поле-объект из JSON."""
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Поле {key!r} должно быть JSON-объектом")
    return value


def _mapping_value(value: object, field_name: str) -> dict[str, Any]:
    """Проверяет, что элемент списка является JSON-объектом."""
    if not isinstance(value, dict):
        raise ValueError(f"Элемент {field_name!r} должен быть JSON-объектом")
    return value


def _list(payload: dict[str, Any], key: str) -> list[object]:
    """Возвращает обязательное поле-список из JSON."""
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Поле {key!r} должно быть JSON-массивом")
    return value


def _string(payload: dict[str, Any], key: str) -> str:
    """Возвращает обязательное строковое поле из JSON."""
    value = payload.get(key)
    return _string_value(value, key)


def _string_value(value: object, field_name: str) -> str:
    """Проверяет значение строкового поля."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Поле {field_name!r} должно быть непустой строкой")
    return value


def _integer(payload: dict[str, Any], key: str) -> int:
    """Возвращает обязательное целое поле из JSON."""
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Поле {key!r} должно быть целым числом")
    return value


def _coordinates(
    payload: dict[str, Any],
    latitude_key: str,
    longitude_key: str | None = None,
) -> tuple[float, float]:
    """Читает пару координат и возвращает ``(latitude, longitude)``."""
    if longitude_key is None:
        longitude_key = "lon"
    latitude = payload.get(latitude_key)
    longitude = payload.get(longitude_key)
    if isinstance(latitude, bool) or not isinstance(latitude, (int, float)):
        raise ValueError(f"Поле {latitude_key!r} должно быть числом")
    if isinstance(longitude, bool) or not isinstance(longitude, (int, float)):
        raise ValueError(f"Поле {longitude_key!r} должно быть числом")
    return float(latitude), float(longitude)


def _mapped_value(
    value: str,
    mapping: dict[str, Skill | VehicleType | Priority],
    field_name: str,
) -> Skill | VehicleType | Priority:
    """Переводит внешний код JSON в значение внутреннего справочника."""
    try:
        return mapping[value.strip().lower()]
    except KeyError as exc:
        allowed = ", ".join(sorted(mapping))
        raise ValueError(
            f"{field_name} содержит неизвестный код {value!r}; допустимы: {allowed}"
        ) from exc
