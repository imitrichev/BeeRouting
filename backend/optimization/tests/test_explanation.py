"""Тесты двухступенчатого decision trace для объяснения маршрута."""

from backend.optimization import (
    Engineer,
    EngineerAvailability,
    ExplanationEngine,
    OptimizationProblem,
    OptimizerConfig,
    ORToolsOptimizer,
    Skill,
    Task,
    TaskStatus,
    VehicleType,
)


def _problem(
    engineers: tuple[Engineer, ...],
    task: Task,
    distance_to_task: dict[str, float],
) -> OptimizationProblem:
    """Создаёт маленький сценарий с разными стартами инженеров."""
    locations = {"job", *(engineer.start_location_id for engineer in engineers)}
    travel_time = {
        source: {
            destination: 0 if source == destination else 1
            for destination in locations
        }
        for source in locations
    }
    distance = {
        source: {
            destination: (
                0.0
                if source == destination
                else distance_to_task.get(source, 1.0)
                if destination == "job"
                else 1.0
            )
            for destination in locations
        }
        for source in locations
    }
    return OptimizationProblem(
        engineers=engineers,
        availabilities=tuple(
            EngineerAvailability(engineer.id, "09:00", "18:00")
            for engineer in engineers
        ),
        tasks=(task,),
        travel_time_matrix=travel_time,
        travel_distance_matrix=distance,
    )


def test_trace_marks_only_engineer_skill_as_important() -> None:
    """JSON выделяет уникальную квалификацию и причину отказа второго инженера."""
    engineers = (
        Engineer(
            "e1",
            "Иванов",
            frozenset({Skill.EMERGENCY_WORKS}),
            "base-1",
            VehicleType.CAR,
        ),
        Engineer(
            "e2",
            "Петров",
            frozenset({Skill.LOCAL_WORKS}),
            "base-2",
            VehicleType.CAR,
        ),
    )
    task = Task(
        "job",
        "job",
        frozenset({Skill.EMERGENCY_WORKS}),
        30,
        "09:00",
        "17:00",
    )
    problem = _problem(engineers, task, {"base-1": 1.0, "base-2": 1.0})
    result = ORToolsOptimizer().optimize(problem)

    trace = ExplanationEngine().explain_task(problem, result, "job")

    assert trace["assignment_reasons"][0]["type"] == "ONLY_ENGINEER_WITH_REQUIRED_SKILL"
    assert trace["assignment_reasons"][0]["must_mention"] is True
    rejected = next(item for item in trace["checks"] if item["engineer"]["id"] == "e2")
    assert rejected["hard_reasons"][0]["type"] == "MISSING_SKILL"
    assert rejected["hard_reasons"][0]["must_mention"] is True


def test_trace_runs_counterfactual_for_feasible_alternative() -> None:
    """Вторая ступень сравнивает допустимое альтернативное назначение."""
    engineers = (
        Engineer(
            "e1",
            "Иванов",
            frozenset({Skill.LOCAL_WORKS}),
            "base-1",
            VehicleType.CAR,
        ),
        Engineer(
            "e2",
            "Петров",
            frozenset({Skill.LOCAL_WORKS}),
            "base-2",
            VehicleType.CAR,
        ),
    )
    task = Task(
        "job",
        "job",
        frozenset({Skill.LOCAL_WORKS}),
        30,
        "09:00",
        "17:00",
    )
    problem = _problem(engineers, task, {"base-1": 1.0, "base-2": 5.0})
    config = OptimizerConfig(explanation_time_limit_seconds=1)
    result = ORToolsOptimizer(config).optimize(problem)

    trace = ExplanationEngine(ORToolsOptimizer(config), config).explain_task(
        problem,
        result,
        "job",
    )

    alternative = next(item for item in trace["checks"] if item["engineer"]["id"] == "e2")
    assert alternative["stage_2"]["status"] == "feasible"
    assert alternative["stage_2"]["distance_delta_km"] == 4.0
    assert alternative["stage_2"]["must_mention"] is False
    assert alternative["impact"] is None


def test_counterfactual_objective_includes_new_engineer_penalty() -> None:
    """Добавление инженера учитывается в objective counterfactual-расчёта."""
    engineers = (
        Engineer(
            "e1",
            "Иванов",
            frozenset({Skill.EMERGENCY_WORKS, Skill.LOCAL_WORKS}),
            "base-1",
            VehicleType.CAR,
        ),
        Engineer(
            "e2",
            "Петров",
            frozenset({Skill.LOCAL_WORKS}),
            "base-2",
            VehicleType.CAR,
        ),
    )
    tasks = (
        Task(
            "emergency-job",
            "emergency-job",
            frozenset({Skill.EMERGENCY_WORKS}),
            30,
            "09:00",
            "18:00",
        ),
        Task(
            "local-job",
            "local-job",
            frozenset({Skill.LOCAL_WORKS}),
            30,
            "09:00",
            "18:00",
        ),
    )
    locations = {"base-1", "base-2", "emergency-job", "local-job"}
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
    problem = OptimizationProblem(
        engineers=engineers,
        availabilities=(
            EngineerAvailability("e1", "09:00", "18:00"),
            EngineerAvailability("e2", "09:00", "18:00"),
        ),
        tasks=tasks,
        travel_time_matrix=travel_time,
        travel_distance_matrix=distance,
    )
    config = OptimizerConfig(
        used_engineers_penalty=1_000,
        distance_penalty_per_km=0,
        travel_time_penalty_per_minute=0,
        explanation_time_limit_seconds=1,
    )
    optimizer = ORToolsOptimizer(config)
    result = optimizer.optimize(problem)
    assert result.used_engineers_count == 1

    trace = ExplanationEngine(optimizer, config).explain_task(
        problem,
        result,
        "local-job",
    )
    alternative = next(item for item in trace["checks"] if item["engineer"]["id"] == "e2")
    stage_2 = alternative["stage_2"]

    assert stage_2["status"] == "feasible"
    assert stage_2["current_used_engineers_count"] == 1
    assert stage_2["alternative_used_engineers_count"] == 2
    assert stage_2["objective"]["delta"]["used_engineers_penalty"] == 1_000
    assert stage_2["objective_delta"] == 1_000
    assert stage_2["must_mention"] is False
    assert alternative["impact"] is None


def test_explanation_disruption_penalty_starts_after_two_reassignments() -> None:
    """Первые два переноса бесплатны, третий стоит 300 баллов."""
    config = OptimizerConfig(
        explanation_free_reassignments=2,
        explanation_reassignment_penalty=300,
    )

    assert config.explanation_plan_disruption_penalty(0) == 0
    assert config.explanation_plan_disruption_penalty(2) == 0
    assert config.explanation_plan_disruption_penalty(3) == 300
    assert config.explanation_plan_disruption_penalty(5) == 900


def test_explanation_does_not_move_closed_task_in_full_recalculation() -> None:
    """Даже при ignore statuses stage 2 не предлагает перенос закрытой заявки."""
    engineers = (
        Engineer("e1", "Иванов", frozenset({Skill.LOCAL_WORKS}), "base-1", VehicleType.CAR),
        Engineer("e2", "Петров", frozenset({Skill.LOCAL_WORKS}), "base-2", VehicleType.CAR),
    )
    task = Task(
        "job",
        "job",
        frozenset({Skill.LOCAL_WORKS}),
        30,
        "09:00",
        "17:00",
        status=TaskStatus.COMPLETED,
    )
    original = _problem(engineers, task, {"base-1": 1.0, "base-2": 5.0})
    problem = OptimizationProblem(
        engineers=original.engineers,
        availabilities=original.availabilities,
        tasks=original.tasks,
        travel_time_matrix=original.travel_time_matrix,
        travel_distance_matrix=original.travel_distance_matrix,
        ignore_task_statuses=True,
    )
    result = ORToolsOptimizer().optimize(problem)

    trace = ExplanationEngine().explain_task(problem, result, "job")
    assigned_id = trace["assignment"]["engineer"]["id"]
    alternative = next(
        item for item in trace["checks"] if item["engineer"]["id"] != assigned_id
    )

    assert alternative["feasible_after_stage_1"] is False
    assert alternative["hard_reasons"][0]["code"] == "TASK_STATUS_LOCKED"
    assert "stage_2" not in alternative
