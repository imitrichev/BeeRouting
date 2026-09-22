"""Сервисный слой web MVP между REST API и Optimization Engine."""

from __future__ import annotations

import os
from typing import Any

from backend.optimization import (
    CoordinateRoutingProvider,
    JsonScenario,
    OptimizationProblem,
    OptimizationResult,
    OptimizerConfig,
    ORToolsOptimizer,
    OSRMRoutingProvider,
    create_osrm_provider_from_environment,
    RoutingProvider,
    load_json_scenario_data,
)
from ..models import Engineer, Job, Priority, Skill, Territory, VehicleType
from ..serializers.optimization import OptimizationResultSerializer, DatasetSerializer


DEFAULT_TERRITORY_CODE = "yugo_tsentr"


class OptimizationWebService:
    """Хранит выбранную территорию и вызывает независимое математическое ядро.

    Состояние хранится в памяти, потому что MVP рассчитан на одного локального
    пользователя. Dataset больше не читается из файла — его роль теперь
    играет территория (``Territory``) вместе со связанными моделями
    ``Engineer``/``Job`` в БД. Этот класс можно позже заменить репозиторием
    без изменений в Optimization Engine.
    """

    def __init__(self) -> None:
        """Создаёт сервис без выбранной территории."""
        self._scenario: JsonScenario | None = None
        self._territory_code: str | None = None
        self.routing_provider: RoutingProvider | None = None
        self.use_osrm = True

    def reset(self) -> None:
        """Очищает dataset; используется тестами и локальной перезагрузкой."""
        self._scenario = None
        self._territory_code = None
        self.routing_provider = None

    def load_territory(self, territory_code: str) -> JsonScenario:
        """Строит dataset из моделей БД для указанной территории."""
        try:
            territory = Territory.objects.get(code=territory_code)
        except Territory.DoesNotExist as exc:
            raise ValueError(
                f"Территория '{territory_code}' не найдена"
            ) from exc

        payload = self._build_scenario_payload(territory)
        payload["scenario"] = f'{payload["territory_code"]}_day'
        scenario = load_json_scenario_data(payload)
        self._scenario = scenario
        self._territory_code = territory.code
        # У новой территории другой набор координат, поэтому старый provider и
        # его кэш ответов больше нельзя использовать.
        self.routing_provider = None
        return scenario

    def current_dataset(self) -> JsonScenario:
        """Возвращает текущий dataset, по умолчанию — территорию по умолчанию."""
        if self._scenario is None:
            return self.load_territory(DEFAULT_TERRITORY_CODE)
        return self._scenario

    def optimize_current(self) -> tuple[JsonScenario, OptimizationResult]:
        """Строит задачу и запускает OR-Tools для текущего dataset."""
        scenario = self.current_dataset()
        problem = self._build_problem(scenario)
        # Для интерактивного MVP оставляем короткий лимит поиска. Он является
        # параметром OR-Tools, а не ограничением корректности hard constraints.
        result = ORToolsOptimizer(
            OptimizerConfig(time_limit_minutes=1)
        ).optimize(problem)
        return scenario, result

    def _build_problem(self, scenario: JsonScenario) -> OptimizationProblem:
        """Добавляет к импортированным сущностям routing data.

        В обычном web-запуске используется OSRM. Тесты переключают
        ``use_osrm`` в ``False`` и получают воспроизводимую локальную матрицу.
        """
        if self.routing_provider is not None:
            provider = self.routing_provider
        elif self.use_osrm:
            provider = create_osrm_provider_from_environment(
                coordinates=scenario.location_coordinates,
                request_timeout_seconds=float(
                    os.getenv("OSRM_TIMEOUT_SECONDS", "15")
                ),
            )
        else:
            provider = CoordinateRoutingProvider(
                coordinates=scenario.location_coordinates,
                speed_km_per_hour=30.0,
            )
        self.routing_provider = provider
        vehicle_types = tuple(
            dict.fromkeys(engineer.vehicle_type for engineer in scenario.engineers)
        )
        return scenario.to_problem(provider, vehicle_types=vehicle_types)

    def _build_scenario_payload(self, territory: Territory) -> dict[str, Any]:
        """Собирает JSON-совместимый payload из моделей БД для territory.

        Формат совпадает со схемой прежних файловых датасетов, поэтому
        дальше он передаётся в тот же ``load_json_scenario_data`` без
        изменений в Optimization Engine.
        """
        engineers = (
            Engineer.objects.filter(territory=territory)
            .select_related("vehicle_type")
            .prefetch_related("skills")
        )
        jobs = (
            Job.objects.filter(territory=territory)
            .select_related(
                "skill_required", "priority", "required_vehicle",
                "district", "time_norm", "reference_engineer",
            )
        )

        dictionaries = {
            "skills": [
                {"code": skill.code, "name": skill.name}
                for skill in Skill.objects.all()
            ],
            "vehicle_types": [
                {"code": vehicle_type.code, "name": vehicle_type.name}
                for vehicle_type in VehicleType.objects.all()
            ],
            "priorities": [
                {"code": priority.code, "name": priority.name}
                for priority in Priority.objects.all()
            ],
        }

        office_start_point = None
        if territory.office_lat is not None and territory.office_lon is not None:
            office_start_point = {
                "lat": float(territory.office_lat),
                "lon": float(territory.office_lon),
            }

        return {
            "territory_code": territory.code,
            "territory_name": territory.name,
            "office_start_point": office_start_point,
            "dictionaries": dictionaries,
            "engineers": [
                {
                    "engineer_id": engineer.engineer_id,
                    "name": engineer.name,
                    "start_lat": float(engineer.start_lat),
                    "start_lon": float(engineer.start_lon),
                    "shift_start": engineer.shift_start.strftime("%H:%M"),
                    "shift_end": engineer.shift_end.strftime("%H:%M"),
                    "skills": [skill.code for skill in engineer.skills.all()],
                    "vehicle_type": engineer.vehicle_type.code,
                }
                for engineer in engineers
            ],
            "jobs": [
                {
                    "job_id": job.job_id,
                    "territory_code": territory.code,
                    "territory_name": territory.name,
                    "request_id": job.request_id,
                    "control_request_id": job.control_request_id,
                    "skill_required": job.skill_required.code,
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
                    "time_norm_code": (
                        job.time_norm.code if job.time_norm else None
                    ),
                    "priority": job.priority.code,
                    "required_vehicle": (
                        job.required_vehicle.code
                        if job.required_vehicle else None
                    ),
                    "reference_status": job.reference_status,
                    "reference_crew": (
                        job.reference_engineer.name
                        if job.reference_engineer else None
                    ),
                    "gigabit": job.gigabit,
                }
                for job in jobs
            ],
        }

    def serialize_dataset(self, scenario: JsonScenario) -> dict[str, Any]:
        """Сериализует dataset для Vue-таблиц и карты."""
        serializer = DatasetSerializer(
            instance=scenario,
            context={
                "source_name": self._territory_code,
            },
        )

        return dict(serializer.data)

    def serialize_response(
        self,
        scenario: JsonScenario,
        result: OptimizationResult | None = None,
    ) -> dict[str, Any]:
        """Возвращает dataset и, если есть, результат оптимизации."""
        response: dict[str, Any] = {"dataset": self.serialize_dataset(scenario)}
        if result is not None:
            response["result"] = self._serialize_result(scenario, result)
        return response

    def _serialize_result(
        self,
        scenario: JsonScenario,
        result: OptimizationResult,
    ) -> dict[str, Any]:
        """Преобразует маршруты и метрики OptimizationResult в JSON."""

        serializer = OptimizationResultSerializer(
            result,
            context={
                "scenario": scenario,
                "routing_provider": self.routing_provider,
            }
        )
        return serializer.data


optimization_service = OptimizationWebService()