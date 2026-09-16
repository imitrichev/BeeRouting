"""Минимальные тесты ручного планирования и проверки hard constraints."""

import pytest

from backend.optimization import (
    Engineer,
    EngineerAvailability,
    InMemoryRoutingProvider,
    ManualAssignmentError,
    ManualAssignmentPlan,
    ManualAssignmentPlanner,
    OptimizationProblem,
    Skill,
    Task,
    TaskStatus,
    VehicleType,
)


def _problem(*tasks: Task) -> OptimizationProblem:
    """Создаёт маленькую задачу с нулевым временем движения."""
    locations = {"base", *(task.location_id for task in tasks)}
    time_matrix = {
        source: {destination: 0 for destination in locations}
        for source in locations
    }
    distance_matrix = {
        source: {destination: 0.0 for destination in locations}
        for source in locations
    }
    return OptimizationProblem(
        engineers=(
            Engineer(
                id="engineer-1",
                name="Инженер",
                qualifications=frozenset({Skill.LOCAL_WORKS}),
                start_location_id="base",
                vehicle_type=VehicleType.CAR,
            ),
        ),
        availabilities=(EngineerAvailability("engineer-1", "09:00", "12:00"),),
        tasks=tuple(tasks),
        travel_time_matrix=time_matrix,
        travel_distance_matrix=distance_matrix,
    )


def test_add_task_commits_only_a_plan_without_hard_constraint_violation() -> None:
    """Недопустимая ручная заявка не изменяет уже сохранённый план."""
    first = Task(
        "task-1", "location-1", frozenset({Skill.LOCAL_WORKS}), 30, "09:00", "10:00"
    )
    equipment_task = Task(
        "task-2",
        "location-2",
        frozenset({Skill.LOCAL_WORKS}),
        30,
        "09:00",
        "10:00",
        required_equipment=frozenset({"meter"}),
    )
    problem = _problem(first, equipment_task)
    plan = ManualAssignmentPlan()

    plan.add_task(problem, "engineer-1", "task-1")
    assert plan.validate(problem).valid
    with pytest.raises(ManualAssignmentError) as error:
        plan.add_task(problem, "engineer-1", "task-2")

    assert plan.assignments_by_engineer == {"engineer-1": ["task-1"]}
    assert error.value.violations[0].code == "missing_equipment"


def test_cancelled_task_does_not_occupy_time_in_manual_plan() -> None:
    """После отменённой заявки активная заявка может начаться в том же окне."""
    cancelled = Task(
        "cancelled",
        "location-cancelled",
        frozenset({Skill.LOCAL_WORKS}),
        90,
        "09:00",
        "10:00",
        status=TaskStatus.CANCELLED,
    )
    active = Task(
        "active",
        "location-active",
        frozenset({Skill.LOCAL_WORKS}),
        90,
        "09:00",
        "10:00",
    )
    problem = _problem(cancelled, active)
    planner = ManualAssignmentPlanner(
        {"engineer-1": ["cancelled", "active"]}
    )

    validation = planner.validate(problem)
    result = planner.optimize(problem)

    assert validation.valid
    assert [stop.task_id for stop in result.routes["engineer-1"].stops] == ["active"]
    assert result.assigned_task_count == 1
    assert result.unassigned_task_count == 0


def test_manual_plan_allows_multiple_tasks_in_one_window_when_they_fit() -> None:
    """Две работы по 45 минут помещаются в одно двухчасовое окно."""
    first = Task(
        "first", "location-first", frozenset({Skill.LOCAL_WORKS}), 45, "09:00", "11:00"
    )
    second = Task(
        "second", "location-second", frozenset({Skill.LOCAL_WORKS}), 45, "09:00", "11:00"
    )
    problem = _problem(first, second)
    planner = ManualAssignmentPlanner({"engineer-1": ["first", "second"]})

    result = planner.optimize(problem)

    assert result.assigned_task_count == 2
    assert [stop.service_start_time for stop in result.routes["engineer-1"].stops] == [
        "09:00",
        "09:45",
    ]
