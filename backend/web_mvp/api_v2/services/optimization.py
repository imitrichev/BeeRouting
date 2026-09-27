"""Сервис API v2: планирование территории и сохранение результата в БД.

Класс расширяет проверенный domain-сервис web MVP операциями API v2. Это
сохраняет разработанную коллегой границу ``views -> service -> optimization``:
представления не собирают математическую задачу и не управляют снимками сами.
"""
import copy
import json
from dataclasses import replace
from typing import Any
from django.db import transaction
from backend.optimization import (
    TaskStatus,
    create_osrm_provider_from_environment,
    load_json_scenario_data,
)
from .planning import OFFICIAL_DATASET_PATHS, PlanningService
from ..models import (
    District, Engineer, Job, Priority, ReassignmentProposal, RescheduleEvent,
    Skill, Territory, VehicleType,
)
from .state import encode, decode
from .repository import sync_entities

STATE_FIELDS = ('_scenario', '_problem', '_result', '_preserve_assigned_tasks',
                '_ignore_task_statuses', '_consider_equipment', '_unavailable_engineer_ids', '_source_name',
                '_late_day_manual_task_ids', '_late_day_active_engineer_ids')


class OptimizationWebService(PlanningService):
    """Актуальный сервис планирования, адресованный конкретной территории.

    Исходная реализация коллеги ввела отдельный сервис и метод
    ``load_territory``. Текущая версия сохраняет этот контракт, но восстанавливает
    уже рассчитанный domain-снимок, поэтому переключение района не запускает
    OR-Tools или OSRM повторно.
    """

    def __init__(self) -> None:
        """Создаёт domain-сервис и запоминает код выбранной территории."""
        super().__init__()
        self._territory_code: str | None = None

    def load_territory(self, territory_code: str):
        """Загружает сохранённый план территории и возвращает её scenario."""
        try:
            territory = Territory.objects.get(code=territory_code)
        except Territory.DoesNotExist as exc:
            raise ValueError(f"Территория {territory_code!r} не найдена") from exc
        restored = restore(territory)
        self.__dict__.update(restored.__dict__)
        self._territory_code = territory.code
        return self.current_dataset()

    def reload_reference_distribution(self):
        """Читает свежий JSON района и заменяет текущий план контрольным."""
        for path in OFFICIAL_DATASET_PATHS:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("territory_code") == self._territory_code:
                scenario = load_json_scenario_data(payload)
                return self.apply_reference_distribution(scenario, path.name)
        raise ValueError(
            f"Официальный JSON района {self._territory_code!r} не найден"
        )

    def rebuild_territory_from_models(self, territory: Territory):
        """Пересобирает domain-сценарий после CRUD-изменений моделей API v2.

        Метод основан на ``_build_scenario_payload`` из реализации коллеги.
        Рассчитанный ранее маршрут сбрасывается, поскольку после изменения
        входных сущностей он больше не является доказанно допустимым.
        """
        scenario = load_json_scenario_data(self._build_scenario_payload(territory))
        jobs_by_id = {
            job.job_id: job
            for job in territory.jobs.select_related("current_engineer")
        }
        status_aliases = {
            "Не отправлена": TaskStatus.NOT_SENT,
            "Отправлена": TaskStatus.NOT_SENT,
            "Назначена": TaskStatus.ASSIGNED,
            "В пути": TaskStatus.EN_ROUTE,
            "В работе": TaskStatus.IN_PROGRESS,
            "Выполнена": TaskStatus.COMPLETED,
            "Отменена": TaskStatus.CANCELLED,
            "Просрочена": TaskStatus.OVERDUE,
        }
        tasks = []
        for task in scenario.tasks:
            job = jobs_by_id.get(task.id)
            if job is None:
                tasks.append(task)
                continue
            raw_status = str(job.current_status or TaskStatus.NOT_SENT.value)
            current_status = status_aliases.get(raw_status)
            if current_status is None:
                try:
                    current_status = TaskStatus(raw_status)
                except ValueError:
                    current_status = TaskStatus.NOT_SENT
            tasks.append(
                replace(
                    task,
                    status=current_status,
                    current_engineer_id=(
                        job.current_engineer.engineer_id
                        if job.current_engineer is not None
                        else None
                    ),
                )
            )
        self._scenario = replace(scenario, tasks=tuple(tasks))
        self._territory_code = territory.code
        self._source_name = territory.source_name or territory.code
        self._problem = None
        self._result = None
        self.routing_provider = None
        self._manual_reassignment_proposals.clear()
        return self._scenario

    def _build_scenario_payload(self, territory: Territory) -> dict[str, Any]:
        """Преобразует ORM-модели коллеги в официальный JSON-контракт ядра."""
        engineers = (
            Engineer.objects.filter(territory=territory)
            .select_related("vehicle_type")
            .prefetch_related("skills")
            .order_by("id")
        )
        jobs = (
            Job.objects.filter(territory=territory)
            .select_related(
                "skill_required", "priority", "required_vehicle", "district",
                "time_norm", "reference_engineer", "current_engineer",
            )
            .order_by("id")
        )
        office = None
        if territory.office_lat is not None and territory.office_lon is not None:
            office = {
                "lat": float(territory.office_lat),
                "lon": float(territory.office_lon),
                "address": territory.office_address,
            }
        source = territory.source_payload or {}
        return {
            "scenario": source.get("scenario", f"{territory.code}_day"),
            "territory_code": territory.code,
            "territory_name": territory.name,
            "office_start_point": office,
            "dictionaries": {
                "skills": [
                    {"code": item.code, "name": item.name}
                    for item in Skill.objects.all().order_by("code")
                ],
                "vehicle_types": [
                    {"code": item.code, "name": item.name}
                    for item in VehicleType.objects.all().order_by("code")
                ],
                "priorities": [
                    {"code": item.code, "name": item.name}
                    for item in Priority.objects.all().order_by("code")
                ],
            },
            "time_norms": source.get("time_norms", []),
            "engineers": [
                {
                    "engineer_id": item.engineer_id,
                    "name": item.name,
                    "start_address": item.start_address,
                    "start_lat": float(item.start_lat),
                    "start_lon": float(item.start_lon),
                    "shift_start": item.shift_start.strftime("%H:%M"),
                    "shift_end": item.shift_end.strftime("%H:%M"),
                    "skills": [
                        self._json_skill_code(skill.code)
                        for skill in item.skills.all()
                    ],
                    "vehicle_type": self._json_vehicle_code(
                        item.vehicle_type.code
                    ),
                    "available_equipment": item.available_equipment,
                    "available_router_count": item.available_router_count,
                }
                for item in engineers
            ],
            "jobs": [self._job_payload(item, territory) for item in jobs],
        }

    @staticmethod
    def _job_payload(job: Job, territory: Territory) -> dict[str, Any]:
        """Сериализует одну ORM-заявку без потери operational status."""
        return {
            "job_id": job.job_id,
            "territory_code": territory.code,
            "territory_name": territory.name,
            "request_id": job.request_id,
            "control_request_id": job.control_request_id,
            "skill_required": OptimizationWebService._json_skill_code(
                job.skill_required.code
            ),
            "skill_required_ru": job.skill_required.name,
            "request_type_bk": job.request_type_bk,
            "request_type_hd": job.request_type_hd,
            "district": job.district.name,
            "address": job.address,
            "lat": float(job.lat),
            "lon": float(job.lon),
            "window_start": job.window_start.strftime("%H:%M"),
            "window_end": job.window_end.strftime("%H:%M"),
            "duration_min": job.duration_min,
            "time_norm_code": job.time_norm.code if job.time_norm else None,
            "priority": job.priority.code.lower(),
            "required_vehicle": (
                OptimizationWebService._json_vehicle_code(
                    job.required_vehicle.code
                ) if job.required_vehicle else None
            ),
            "required_equipment": job.required_equipment,
            "required_router_count": job.required_router_count,
            "status": OptimizationWebService._json_status(job.current_status),
            "current_engineer_id": (
                job.current_engineer.engineer_id if job.current_engineer else None
            ),
            "reference_status": job.reference_status,
            "reference_crew": (
                job.reference_engineer.name if job.reference_engineer else None
            ),
            "gigabit": job.gigabit,
        }

    @staticmethod
    def _json_skill_code(code: str) -> str:
        """Возвращает код навыка официального JSON для domain/ORM-кода."""
        return {
            "LOCAL_WORKS": "local_works",
            "CONNECTION_AND_UPSELL": "connection_orders",
            "EMERGENCY_WORKS": "emergency_works",
        }.get(code, code.lower())

    @staticmethod
    def _json_vehicle_code(code: str) -> str:
        """Возвращает внешний код транспорта; WALK в dataset называется foot."""
        return {"WALK": "foot"}.get(code, code.lower())

    @staticmethod
    def _json_status(status: str) -> str:
        """Преобразует domain-статус в поддерживаемое русское значение JSON."""
        return {
            "NOT_SENT": "Не отправлена",
            "ASSIGNED": "Назначена",
            "EN_ROUTE": "В пути",
            "IN_PROGRESS": "В работе",
            "COMPLETED": "Выполнена",
            "CANCELLED": "Отменена",
            "OVERDUE": "Просрочена",
        }.get(status, status)


def rebuild_after_crud(territory: Territory) -> None:
    """Публикует согласованный снимок после изменения через ORM ViewSet."""
    service = OptimizationWebService()
    service.rebuild_territory_from_models(territory)
    save(territory, service)


def restore(territory):
    """Создаёт изолированный сервис для одного запроса и одного района."""
    service = OptimizationWebService()
    service._territory_code = territory.code
    for name, value in territory.state.items():
        if name in STATE_FIELDS:
            setattr(service, name, decode(value))
    # Поддерживаем снимки, сохранённые до разделения reference и operational
    # статусов: построенный маршрут является источником текущих назначений.
    if service._result is not None:
        service._project_result_to_scenario()
    if service._problem is not None:
        service.routing_provider = create_osrm_provider_from_environment(
            coordinates=service._scenario.location_coordinates,
            request_timeout_seconds=15.0,
        )
    return service


def save(territory, service):
    """Атомарно сохраняет модели ядра, матрицы, результат и геометрию."""
    # Сначала переносим фактические назначения из результата в domain-снимок.
    # Иначе после следующего HTTP-запроса restore снова прочитает статусы и
    # исполнителей из контрольного JSON.
    service._project_result_to_scenario()
    response = service.serialize_response(service._scenario, service._result)
    response['planning_options'] = {
        'ignore_task_statuses': service._ignore_task_statuses,
        'preserve_assigned_tasks': service._preserve_assigned_tasks,
        'consider_equipment': service._consider_equipment,
        'planning_time': (
            service._problem.planning_time if service._problem is not None else None
        ),
    }
    territory.state = {name: encode(getattr(service, name)) for name in STATE_FIELDS}
    territory.response = response
    territory.revision += 1
    territory.save()
    sync_entities(territory, service)
    # При отсутствии маршрута исходный JSON скрывает reference-статусы.
    # После ручной смены статуса нужно сразу отразить operational-состояние
    # из ORM, иначе диспетчер увидит старое «не отправлена» до нового GET.
    response['dataset'] = public_dataset_response(territory).get(
        'dataset', response.get('dataset')
    )
    territory.response = response
    territory.save(update_fields=['response'])
    ReassignmentProposal.objects.filter(territory=territory).delete()
    return response


def public_dataset_response(territory):
    """Возвращает сохранённый dataset без контрольных статусов до расчёта.

    Старые записи в БД могли быть сохранены до введения правила скрытия
    ``reference_status``. Поэтому одного изменения сериализатора недостаточно:
    GET существующего района читает готовый JSON из ``Territory.response``.
    Здесь выполняется безопасная копия только для выдачи API, не меняя снимок
    в базе и не затрагивая статусы, которые нужны solver для контрольного
    режима после запуска.
    """
    response = copy.deepcopy(territory.response or {})
    if response.get("result") is not None:
        return response

    dataset = response.get("dataset")
    if not isinstance(dataset, dict):
        return response

    for task in dataset.get("tasks", []):
        if isinstance(task, dict):
            task["status"] = "NOT_SENT"
            task["current_engineer_id"] = None
            task["assignment_locked"] = False
    operational_jobs = {
        job.job_id: job
        for job in territory.jobs.only("job_id", "current_status", "current_engineer_id")
    }
    for task in dataset.get("tasks", []):
        if not isinstance(task, dict):
            continue
        job = operational_jobs.get(task.get("id"))
        if job is None:
            continue
        task["status"] = job.current_status
        task["current_engineer_id"] = (
            job.current_engineer.engineer_id
            if job.current_engineer_id
            else None
        )
    return response


@transaction.atomic
def import_dataset(content, filename):
    """Регистрирует район при первой загрузке; повторная загрузка сохраняет его план."""
    payload = json.loads(content.decode('utf-8'))
    scenario = load_json_scenario_data(payload)
    # Контрольные статусы и исполнители в официальном JSON описывают
    # исторический план организаторов, а не текущее состояние диспетчера.
    # Новый район всегда начинается с чистой очереди заявок. Исходный payload
    # сохраняется в Territory.source_payload и остаётся доступен benchmark.
    scenario = replace(
        scenario,
        tasks=tuple(
            replace(
                task,
                status=TaskStatus.NOT_SENT,
                current_engineer_id=None,
            )
            for task in scenario.tasks
        ),
    )
    code = payload.get('territory_code') or scenario.scenario_name
    territory = Territory.objects.filter(code=code).first()
    if territory is not None and territory.state:
        return territory
    service = OptimizationWebService()
    service._scenario = scenario
    service._source_name = filename
    office = payload.get('office_start_point') or {}
    territory, _ = Territory.objects.update_or_create(
        code=code,
        defaults={
            'name': payload.get('territory_name') or code,
            'office_lat': office.get('lat'), 'office_lon': office.get('lon'),
            'office_address': office.get('address', ''), 'source_name': filename,
            'source_payload': payload,
        },
    )
    save(territory, service)
    return territory


@transaction.atomic
def reload_official_datasets(paths):
    """Удаляет всё состояние районов и заново импортирует официальные JSON.

    Удаление ``Territory`` каскадно очищает инженеров, заявки, события
    перепланирования и предложения ручного назначения. Поэтому старые планы,
    ревизии и результаты не могут смешаться с повторно загруженными данными.
    """
    # Job защищает District через PROTECT, поэтому очищаем связанные таблицы
    # явно, от наиболее зависимых сущностей к владельцу территории.
    ReassignmentProposal.objects.all().delete()
    RescheduleEvent.objects.all().delete()
    Job.objects.all().delete()
    Engineer.objects.all().delete()
    District.objects.all().delete()
    Territory.objects.all().delete()
    return [
        import_dataset(path.read_bytes(), path.name)
        for path in paths
    ]
