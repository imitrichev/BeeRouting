"""Общие проверки жёстких ресурсных ограничений."""

from .models import Engineer, OptimizationProblem, Task


def engineer_can_execute_task(
    problem: OptimizationProblem,
    engineer: Engineer,
    task: Task,
) -> bool:
    """Проверяет навыки, оборудование и транспорт инженера."""
    equipment_by_id = {
        resource.id: resource for resource in problem.equipment_resources
    }
    equipment_types = set(engineer.available_equipment)
    equipment_types.update(
        equipment_by_id[resource_id].equipment_type
        for resource_id in engineer.equipment_resource_ids
    )
    vehicle_type = engineer.vehicle_type
    if engineer.vehicle_resource_id is not None:
        vehicle_by_id = {
            resource.id: resource for resource in problem.vehicle_resources
        }
        vehicle_type = vehicle_by_id[engineer.vehicle_resource_id].vehicle_type
    return (
        task.required_skills.issubset(engineer.qualifications)
        and task.required_equipment.issubset(equipment_types)
        and (
            task.required_vehicle_type is None
            or vehicle_type == task.required_vehicle_type
        )
    )


def engineer_has_required_equipment(
    problem: OptimizationProblem,
    engineer: Engineer,
    task: Task,
) -> bool:
    """Проверяет оборудование без проверки остальных ограничений."""
    equipment_by_id = {
        resource.id: resource for resource in problem.equipment_resources
    }
    equipment_types = set(engineer.available_equipment)
    equipment_types.update(
        equipment_by_id[resource_id].equipment_type
        for resource_id in engineer.equipment_resource_ids
    )
    return task.required_equipment.issubset(equipment_types)


def resource_ids_used_for_task(
    problem: OptimizationProblem,
    engineer: Engineer,
    task: Task,
) -> tuple[str, ...]:
    """Возвращает экземпляры ограниченных ресурсов для сервисного интервала."""
    equipment_by_id = {
        resource.id: resource for resource in problem.equipment_resources
    }
    resource_ids: set[str] = set()
    for equipment_type in task.required_equipment:
        if equipment_type in engineer.available_equipment:
            continue
        matching_resources = sorted(
            resource_id
            for resource_id in engineer.equipment_resource_ids
            if equipment_by_id[resource_id].equipment_type == equipment_type
        )
        if matching_resources:
            resource_ids.add(matching_resources[0])
    if engineer.vehicle_resource_id is not None:
        resource_ids.add(engineer.vehicle_resource_id)
    return tuple(sorted(resource_ids))
