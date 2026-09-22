"""Единые правила статусов для всех реализаций планирования."""

import pytest

from backend.optimization import (
    Engineer,
    EngineerAvailability,
    EngineerOperationalState,
    GreedyBaselineOptimizer,
    ManualAssignmentError,
    ManualAssignmentPlan,
    ManualAssignmentPlanner,
    OptimizationProblem,
    OptimizerConfig,
    ORToolsOptimizer,
    Skill,
    Task,
    TaskStatus,
    VehicleType,
)


def _task(
    task_id: str,
    status: TaskStatus,
    *,
    current_engineer_id: str | None = None,
) -> Task:
    """Создаёт заявку с широким окном для проверки только статуса."""
    return Task(
        id=task_id,
        location_id=task_id,
        required_skills=frozenset({Skill.LOCAL_WORKS}),
        duration_minutes=10,
        window_start="09:00",
        window_end="17:00",
        status=status,
        current_engineer_id=current_engineer_id,
    )


def _problem(
    tasks: tuple[Task, ...],
    *,
    preserve_assigned_tasks: bool = False,
) -> OptimizationProblem:
    """Создаёт двух инженеров; первому всегда ближе тестовая заявка."""
    engineers = (
        Engineer(
            "e1",
            "Первый",
            frozenset({Skill.LOCAL_WORKS}),
            "base-1",
            VehicleType.CAR,
        ),
        Engineer(
            "e2",
            "Второй",
            frozenset({Skill.LOCAL_WORKS}),
            "base-2",
            VehicleType.CAR,
        ),
    )
    locations = ("base-1", "base-2", *(task.location_id for task in tasks))
    time_matrix = {
        source: {
            destination: 0 if source == destination else 20
            for destination in locations
        }
        for source in locations
    }
    distance_matrix = {
        source: {
            destination: 0.0 if source == destination else 20.0
            for destination in locations
        }
        for source in locations
    }
    for task in tasks:
        time_matrix["base-1"][task.location_id] = 1
        distance_matrix["base-1"][task.location_id] = 1.0
        time_matrix["base-2"][task.location_id] = 10
        distance_matrix["base-2"][task.location_id] = 10.0
    return OptimizationProblem(
        engineers=engineers,
        availabilities=(
            EngineerAvailability("e1", "09:00", "18:00"),
            EngineerAvailability("e2", "09:00", "18:00"),
        ),
        tasks=tasks,
        travel_time_matrix=time_matrix,
        travel_distance_matrix=distance_matrix,
        preserve_assigned_tasks=preserve_assigned_tasks,
    )


@pytest.mark.parametrize("optimizer", [GreedyBaselineOptimizer(), ORToolsOptimizer()])
def test_cancelled_and_completed_tasks_are_not_planned(optimizer) -> None:
    """Исторические заявки видны в problem, но не входят в маршрут/objective."""
    problem = _problem(
        (
            _task("cancelled", TaskStatus.CANCELLED, current_engineer_id="e1"),
            _task("completed", TaskStatus.COMPLETED, current_engineer_id="e1"),
            _task("open", TaskStatus.NOT_SENT),
        )
    )

    result = optimizer.optimize(problem)

    route_task_ids = {
        stop.task_id for route in result.routes.values() for stop in route.stops
    }
    assert route_task_ids == {"open"}
    assert result.assigned_task_count == 1
    assert result.unassigned_task_count == 0


@pytest.mark.parametrize("status", [TaskStatus.EN_ROUTE, TaskStatus.IN_PROGRESS])
@pytest.mark.parametrize("optimizer", [GreedyBaselineOptimizer(), ORToolsOptimizer()])
def test_started_task_is_fixed_to_current_engineer(status, optimizer) -> None:
    """Начатую заявку нельзя отдать более близкому другому инженеру."""
    task = _task("started", status, current_engineer_id="e2")

    result = optimizer.optimize(_problem((task,)))

    assert [stop.task_id for stop in result.routes["e2"].stops] == ["started"]
    assert result.routes["e1"].stops == ()


@pytest.mark.parametrize("optimizer", [GreedyBaselineOptimizer(), ORToolsOptimizer()])
def test_started_task_is_the_first_active_stop(optimizer) -> None:
    """Новая заявка не может быть вставлена перед уже начатым участком."""
    open_task = _task("open", TaskStatus.NOT_SENT)
    started_task = _task(
        "started",
        TaskStatus.IN_PROGRESS,
        current_engineer_id="e2",
    )

    result = optimizer.optimize(_problem((open_task, started_task)))

    assert result.routes["e2"].stops[0].task_id == "started"


@pytest.mark.parametrize("optimizer", [GreedyBaselineOptimizer(), ORToolsOptimizer()])
def test_assigned_task_can_move_or_be_preserved_by_mode(optimizer) -> None:
    """ASSIGNED переносится в обычном плане и фиксируется в режиме сохранения."""
    task = _task("assigned", TaskStatus.ASSIGNED, current_engineer_id="e2")

    movable = optimizer.optimize(_problem((task,), preserve_assigned_tasks=False))
    preserved = optimizer.optimize(_problem((task,), preserve_assigned_tasks=True))

    assert [stop.task_id for stop in movable.routes["e1"].stops] == ["assigned"]
    assert [stop.task_id for stop in preserved.routes["e2"].stops] == ["assigned"]


@pytest.mark.parametrize("optimizer", [GreedyBaselineOptimizer(), ORToolsOptimizer()])
def test_overdue_task_is_planned_normally(optimizer) -> None:
    """OVERDUE остаётся активной заявкой и получает новый маршрут."""
    result = optimizer.optimize(_problem((_task("overdue", TaskStatus.OVERDUE),)))

    assert result.assigned_task_count == 1
    assert result.unassigned_task_count == 0


@pytest.mark.parametrize("optimizer", [GreedyBaselineOptimizer(), ORToolsOptimizer()])
def test_replanning_continues_from_current_time_and_location(optimizer) -> None:
    """Новый участок маршрута начинается из оперативного снимка, а не с базы."""
    task = _task("next", TaskStatus.NOT_SENT)
    problem = _problem((task,))
    # Текущая позиция совпадает с точкой заявки: дорога должна стать нулевой.
    problem = OptimizationProblem(
        engineers=problem.engineers,
        availabilities=problem.availabilities,
        tasks=problem.tasks,
        travel_time_matrix=problem.travel_time_matrix,
        travel_distance_matrix=problem.travel_distance_matrix,
        planning_time="12:30",
        operational_states=(EngineerOperationalState("e1", "next"),),
    )

    result = optimizer.optimize(problem)

    stop = result.routes["e1"].stops[0]
    assert stop.arrival_time == "12:30"
    assert stop.travel_time_from_previous == 0


def test_replanning_penalty_preserves_existing_assignment() -> None:
    """Небольшая экономия пути не должна переносить уже запланированную заявку."""
    task = _task("planned", TaskStatus.NOT_SENT)
    problem = _problem((task,))
    reference = {"e2": (task.id,)}

    stable = ORToolsOptimizer().optimize(
        problem,
        reference_routes_by_engineer=reference,
    )
    without_stability = ORToolsOptimizer(
        OptimizerConfig(reassignment_penalty=0, route_order_change_penalty=0)
    ).optimize(
        problem,
        reference_routes_by_engineer=reference,
    )

    assert [stop.task_id for stop in stable.routes["e2"].stops] == [task.id]
    assert stable.reassigned_task_count == 0
    assert stable.plan_disruption_penalty == 0
    assert [stop.task_id for stop in without_stability.routes["e1"].stops] == [task.id]
    assert without_stability.reassigned_task_count == 1


def test_manual_planner_uses_the_same_status_filter() -> None:
    """Ручной план не валидирует и не считает отменённые/выполненные работы."""
    problem = _problem(
        (
            _task("cancelled", TaskStatus.CANCELLED, current_engineer_id="e1"),
            _task("completed", TaskStatus.COMPLETED, current_engineer_id="e1"),
            _task("open", TaskStatus.NOT_SENT),
        )
    )
    planner = ManualAssignmentPlanner(
        {"e1": ("cancelled", "completed", "open")}
    )

    assert planner.validate(problem).valid
    result = planner.optimize(problem)
    assert [stop.task_id for stop in result.routes["e1"].stops] == ["open"]
    assert result.unassigned_task_count == 0


def test_manual_add_rejects_cancelled_task() -> None:
    """Диспетчер не может повторно добавить отменённую заявку в новый план."""
    problem = _problem(
        (_task("cancelled", TaskStatus.CANCELLED, current_engineer_id="e1"),)
    )

    with pytest.raises(ManualAssignmentError) as error:
        ManualAssignmentPlan().add_task(problem, "e1", "cancelled")

    assert error.value.violations[0].code == "inactive_task"
