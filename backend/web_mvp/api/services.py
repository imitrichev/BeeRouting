"""Сервисный слой web MVP между REST API и Optimization Engine."""

from __future__ import annotations

import json
import os
from pathlib import Path
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
    load_json_scenario,
    load_json_scenario_data,
)


OFFICIAL_DATASET_PATH = Path(__file__).resolve().parents[3] / "yugo_center.json"


class OptimizationWebService:
    """Хранит выбранный dataset и вызывает независимое математическое ядро.

    Состояние хранится в памяти, потому что MVP рассчитан на одного локального
    пользователя. Позже этот класс можно заменить репозиторием без изменений
    в Optimization Engine.
    """

    def __init__(self) -> None:
        """Создаёт сервис без загруженного пользовательского сценария."""
        self._scenario: JsonScenario | None = None
        self._source_name: str | None = None
        self.routing_provider: RoutingProvider | None = None
        self.use_osrm = True

    def reset(self) -> None:
        """Очищает dataset; используется тестами и локальной перезагрузкой."""
        self._scenario = None
        self._source_name = None
        self.routing_provider = None

    def load_official_dataset(self) -> JsonScenario:
        """Загружает официальный демонстрационный JSON из корня проекта."""
        scenario = load_json_scenario(OFFICIAL_DATASET_PATH)
        self._scenario = scenario
        self._source_name = OFFICIAL_DATASET_PATH.name
        # У нового dataset другой набор координат, поэтому старый provider и
        # его кэш ответов больше нельзя использовать.
        self.routing_provider = None
        return scenario

    def load_uploaded_dataset(self, content: bytes, filename: str) -> JsonScenario:
        """Разбирает загруженный JSON и делает его текущим dataset."""
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Файл должен содержать корректный JSON в UTF-8") from exc
        scenario = load_json_scenario_data(payload)
        self._scenario = scenario
        self._source_name = filename
        self.routing_provider = None
        return scenario

    def current_dataset(self) -> JsonScenario:
        """Возвращает текущий dataset, по умолчанию официальный."""
        if self._scenario is None:
            return self.load_official_dataset()
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

    def serialize_dataset(self, scenario: JsonScenario) -> dict[str, Any]:
        """Преобразует dataset в JSON-ответ для таблиц Vue."""
        return {
            "source_name": self._source_name,
            "scenario_name": scenario.scenario_name,
            "engineers": [
                {
                    "id": engineer.id,
                    "name": engineer.name,
                    "qualifications": [skill.value for skill in engineer.qualifications],
                    "vehicle_type": engineer.vehicle_type.value,
                    "start_location_id": engineer.start_location_id,
                    "start_latitude": engineer.start_latitude,
                    "start_longitude": engineer.start_longitude,
                    "available_from": next(
                        item.available_from
                        for item in scenario.availabilities
                        if item.engineer_id == engineer.id
                    ),
                    "available_until": next(
                        item.available_until
                        for item in scenario.availabilities
                        if item.engineer_id == engineer.id
                    ),
                }
                for engineer in scenario.engineers
            ],
            "tasks": [self._serialize_task(task) for task in scenario.tasks],
        }

    @staticmethod
    def _serialize_task(task) -> dict[str, Any]:
        """Преобразует одну domain-заявку в JSON для таблицы и карты."""
        return {
            "id": task.id,
            "location_id": task.location_id,
            "latitude": task.latitude,
            "longitude": task.longitude,
            "required_skill": next(iter(task.required_skills)).value,
            "duration_minutes": task.duration_minutes,
            "window_start": task.window_start,
            "window_end": task.window_end,
            "priority": task.priority.value,
            "required_vehicle_type": (
                None
                if task.required_vehicle_type is None
                else task.required_vehicle_type.value
            ),
        }

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
        engineers_by_id = {engineer.id: engineer for engineer in scenario.engineers}
        tasks_by_id = {task.id: task for task in scenario.tasks}
        routes = []
        for engineer_id, route in result.routes.items():
            engineer = engineers_by_id[engineer_id]
            route_location_ids = [engineer.start_location_id] + [
                tasks_by_id[stop.task_id].location_id for stop in route.stops
            ]
            geometry = (
                self.routing_provider.get_route_geometry(
                    route_location_ids,
                    engineer.vehicle_type,
                )
                if self.routing_provider is not None
                else None
            )
            routes.append(
                {
                    "engineer_id": engineer_id,
                    "engineer_name": engineer.name,
                    "vehicle_type": engineer.vehicle_type.value,
                    "start_latitude": engineer.start_latitude,
                    "start_longitude": engineer.start_longitude,
                    "total_distance_km": route.total_distance_km,
                    "total_travel_minutes": route.total_travel_minutes,
                    "geometry": geometry,
                    "stops": [
                        {
                            "task_id": stop.task_id,
                            "latitude": tasks_by_id[stop.task_id].latitude,
                            "longitude": tasks_by_id[stop.task_id].longitude,
                            "arrival_time": stop.arrival_time,
                            "service_start_time": stop.service_start_time,
                            "service_end_time": stop.service_end_time,
                            "travel_time_from_previous": stop.travel_time_from_previous,
                            "distance_from_previous_km": stop.distance_from_previous_km,
                        }
                        for stop in route.stops
                    ],
                }
            )
        return {
            "metrics": {
                "assigned_task_count": result.assigned_task_count,
                "unassigned_task_count": result.unassigned_task_count,
                "used_engineers_count": result.used_engineers_count,
                "total_distance_km": result.total_distance,
                "total_travel_minutes": result.total_travel_time,
                "total_objective": result.total_objective,
                "unassigned_penalty": result.unassigned_penalty,
                "used_engineers_penalty": result.used_engineers_penalty,
                "distance_penalty": result.distance_penalty,
                "travel_time_penalty": result.travel_time_penalty,
            },
            "distance_by_engineer": result.distance_by_engineer,
            "travel_time_by_engineer": result.travel_time_by_engineer,
            "routes": routes,
            "unassigned": [
                {
                    "task_id": task_id,
                    "reason_code": reason.code.value,
                    "message": reason.message,
                }
                for task_id, reason in result.unassigned_reasons.items()
            ],
        }


optimization_service = OptimizationWebService()
