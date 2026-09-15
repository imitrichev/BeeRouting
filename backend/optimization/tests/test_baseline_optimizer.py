"""Тесты намеренно простого greedy baseline."""

from backend.optimization import (
    EngineerAvailability,
    GreedyBaselineOptimizer,
    InMemoryRoutingProvider,
    OptimizationProblem,
    ORToolsOptimizer,
    Skill,
    Task,
    VehicleType,
    Engineer,
)


def make_engineer(engineer_id: str, start_location_id: str) -> Engineer:
    """Создаёт одинакового по ограничениям инженера для теста."""
    return Engineer(
        id=engineer_id,
        name=engineer_id,
        qualifications=frozenset({Skill.LOCAL_WORKS}),
        start_location_id=start_location_id,
        vehicle_type=VehicleType.CAR,
    )


def make_task(task_id: str, location_id: str) -> Task:
    """Создаёт заявку с широким окном и короткой работой."""
    return Task(
        id=task_id,
        location_id=location_id,
        required_skills=frozenset({Skill.LOCAL_WORKS}),
        duration_minutes=1,
        window_start="08:00",
        window_end="17:00",
    )


def build_problem() -> OptimizationProblem:
    """Создаёт задачу, в которой greedy выбирает заведомо плохое начало."""
    engineers = (
        make_engineer("e1", "base-1"),
        make_engineer("e2", "base-2"),
    )
    tasks = (
        make_task("t1", "customer-1"),
        make_task("t2", "customer-2"),
    )
    locations = ("base-1", "base-2", "customer-1", "customer-2")
    travel_time = {
        source: {
            destination: 0 if source == destination else 100
            for destination in locations
        }
        for source in locations
    }
    travel_time["base-1"]["customer-1"] = 1
    travel_time["base-2"]["customer-2"] = 1
    travel_time["customer-1"]["customer-2"] = 100
    distance = {
        source: {
            destination: 0.0 if source == destination else 100.0
            for destination in locations
        }
        for source in locations
    }
    distance["base-1"]["customer-1"] = 1.0
    distance["base-2"]["customer-2"] = 1.0
    distance["customer-1"]["customer-2"] = 100.0
    provider = InMemoryRoutingProvider(travel_time, distance)
    availabilities = tuple(
        EngineerAvailability(engineer.id, "08:00", "17:00")
        for engineer in engineers
    )
    return OptimizationProblem(
        engineers=engineers,
        availabilities=availabilities,
        tasks=tasks,
        travel_time_matrix=provider.get_travel_time_matrix(locations),
        travel_distance_matrix=provider.get_distance_matrix(locations),
    )


def build_fewer_engineers_problem() -> OptimizationProblem:
    """Создаёт задачу, где greedy использует два маршрута вместо одного."""
    engineers = (
        make_engineer("e1", "base-1"),
        Engineer(
            id="e2",
            name="e2",
            qualifications=frozenset({Skill.LOCAL_WORKS, Skill.EMERGENCY_WORKS}),
            start_location_id="base-2",
            vehicle_type=VehicleType.CAR,
        ),
    )
    tasks = (
        make_task("t1", "customer-1"),
        Task(
            id="t2",
            location_id="customer-2",
            required_skills=frozenset({Skill.EMERGENCY_WORKS}),
            duration_minutes=1,
            window_start="08:00",
            window_end="17:00",
        ),
    )
    locations = ("base-1", "base-2", "customer-1", "customer-2")
    travel_time = {
        source: {
            destination: 0 if source == destination else 1
            for destination in locations
        }
        for source in locations
    }
    distance = {
        source: {
            destination: 0.0 if source == destination else 1.0
            for destination in locations
        }
        for source in locations
    }
    provider = InMemoryRoutingProvider(travel_time, distance)
    availabilities = tuple(
        EngineerAvailability(engineer.id, "08:00", "17:00")
        for engineer in engineers
    )
    return OptimizationProblem(
        engineers=engineers,
        availabilities=availabilities,
        tasks=tasks,
        travel_time_matrix=provider.get_travel_time_matrix(locations),
        travel_distance_matrix=provider.get_distance_matrix(locations),
    )


def test_baseline_uses_input_order_for_engineers_and_tasks() -> None:
    """Baseline берёт первого допустимого инженера и сохраняет порядок заявок."""
    result = GreedyBaselineOptimizer().optimize(build_problem())

    assert [stop.task_id for stop in result.routes["e1"].stops] == ["t1", "t2"]
    assert result.routes["e2"].stops == ()
    assert result.used_engineers_count == 1
    assert result.assigned_task_count == 2
    assert result.unassigned_task_count == 0


def test_baseline_can_be_worse_than_ortools() -> None:
    """OR-Tools перераспределяет заявки и использует меньше инженеров."""
    problem = build_fewer_engineers_problem()

    baseline = GreedyBaselineOptimizer().optimize(problem)
    optimized = ORToolsOptimizer().optimize(problem)

    assert baseline.used_engineers_count == 2
    assert optimized.used_engineers_count == 1
    assert optimized.assigned_task_count == baseline.assigned_task_count == 2


def test_in_memory_provider_returns_both_routing_matrices() -> None:
    """Provider явно выдаёт время в минутах и расстояние в километрах."""
    problem = build_problem()
    provider = InMemoryRoutingProvider(
        problem.travel_time_matrix,
        problem.travel_distance_matrix,
    )

    assert provider.get_travel_time_matrix(("base-1", "customer-1"))["base-1"][
        "customer-1"
    ] == 1
    assert provider.get_distance_matrix(("base-1", "customer-1"))["base-1"][
        "customer-1"
    ] == 1.0
