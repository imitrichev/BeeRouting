"""Контракты API: optimization."""
from __future__ import annotations

from typing import Any
from rest_framework import serializers
from backend.optimization import JsonScenario, OptimizationResult
from .helpers import UnassignedTaskSerializer
from .engineer import EngineerRouteSerializer, DatasetEngineerSerializer
from .job import DatasetTaskSerializer


class OptimizationMetricsSerializer(serializers.Serializer):
    assigned_task_count = serializers.IntegerField(read_only=True)
    unassigned_task_count = serializers.IntegerField(read_only=True)
    used_engineers_count = serializers.IntegerField(read_only=True)

    total_distance_km = serializers.FloatField(
        source="total_distance",
        read_only=True,
    )
    total_travel_minutes = serializers.FloatField(
        source="total_travel_time",
        read_only=True,
    )
    total_objective = serializers.FloatField(read_only=True)

    unassigned_penalty = serializers.FloatField(read_only=True)
    used_engineers_penalty = serializers.FloatField(read_only=True)
    distance_penalty = serializers.FloatField(read_only=True)
    travel_time_penalty = serializers.FloatField(read_only=True)
    plan_disruption_penalty = serializers.FloatField(read_only=True)
    reassigned_task_count = serializers.IntegerField(read_only=True)
    reordered_task_count = serializers.IntegerField(read_only=True)


class OptimizationResultSerializer(serializers.Serializer):
    """
    Read-only serializer для OptimizationResult.

    Required context:
        scenario: JsonScenario

    Optional context:
        routing_provider: провайдер маршрутизации с методом
        get_route_geometry(location_ids, vehicle_type).
    """

    metrics = OptimizationMetricsSerializer(read_only=True)

    distance_by_engineer = serializers.DictField(
        child=serializers.FloatField(),
        read_only=True,
    )
    travel_time_by_engineer = serializers.DictField(
        child=serializers.FloatField(),
        read_only=True,
    )

    routes = EngineerRouteSerializer(many=True, read_only=True)
    unassigned = UnassignedTaskSerializer(many=True, read_only=True)

    def to_representation(
        self,
        result: OptimizationResult,
    ) -> dict[str, Any]:
        scenario: JsonScenario = self.context["scenario"]

        context = {
            **self.context,
            "engineers_by_id": {
                engineer.id: engineer
                for engineer in scenario.engineers
            },
            "tasks_by_id": {
                task.id: task
                for task in scenario.tasks
            },
        }

        return {
            "metrics": OptimizationMetricsSerializer(result).data,
            "distance_by_engineer": result.distance_by_engineer,
            "travel_time_by_engineer": result.travel_time_by_engineer,
            "routes": EngineerRouteSerializer(
                list(result.routes.items()),
                many=True,
                context=context,
            ).data,
            "unassigned": UnassignedTaskSerializer(
                list(result.unassigned_reasons.items()),
                many=True,
                context=context,
            ).data,
        }


class DatasetSerializer(serializers.Serializer):
    """
    Сериализатор JsonScenario для Vue-таблиц и карты.

    Required context:
        source_name: имя исходного файла, набора данных или источника.
    """

    source_name = serializers.SerializerMethodField()
    scenario_name = serializers.CharField(read_only=True)

    engineers = DatasetEngineerSerializer(
        many=True,
        read_only=True,
    )
    tasks = DatasetTaskSerializer(
        many=True,
        read_only=True,
    )

    def get_source_name(self, scenario: Any) -> str:
        return self.context["source_name"]
