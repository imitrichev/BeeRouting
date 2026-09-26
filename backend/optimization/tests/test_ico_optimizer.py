"""Тесты VRPTW-решателя ICO с random keys."""

from dataclasses import replace

from backend.optimization import (
    ICOOptimizer,
    ICORoutingConfig,
    RouteOptimizer,
    Skill,
    TaskStatus,
    UnassignedReasonCode,
)
from backend.optimization.tests.test_ortools_optimizer import (
    build_problem,
    make_task,
)


def small_search_config() -> ICORoutingConfig:
    """Возвращает быстрый детерминированный профиль для unit-тестов."""
    return ICORoutingConfig(
        countries_count=3,
        country_population=8,
        maximum_iterations=25,
        maximum_function_evaluations=1_500,
        random_seed=42,
    )


def test_ico_optimizer_implements_common_interface_and_assigns_routes() -> None:
    """ICO возвращает общий формат и назначает все допустимые заявки."""
    optimizer = ICOOptimizer(ico_config=small_search_config())

    assert isinstance(optimizer, RouteOptimizer)
    result = optimizer.optimize(build_problem())

    assert result.assigned_task_count == 5
    assert result.unassigned_task_ids == ()
    assert any(len(route.stops) > 1 for route in result.routes.values())
    assert result.total_objective == (
        result.unassigned_penalty
        + result.used_engineers_penalty
        + result.distance_penalty
        + result.travel_time_penalty
        + result.plan_disruption_penalty
    )


def test_ico_optimizer_keeps_impossible_skill_unassigned() -> None:
    """Random keys не превращают отсутствие квалификации в мягкий штраф."""
    original = build_problem()
    impossible = make_task(
        "impossible",
        skill=Skill.CONNECTION_AND_UPSELL,
        location_id="customer-1",
    )
    engineers = tuple(
        engineer
        for engineer in original.engineers
        if Skill.CONNECTION_AND_UPSELL not in engineer.qualifications
    )
    # В исходном наборе после фильтра остаются инженеры без нужного навыка.
    problem = type(original)(
        engineers=engineers,
        availabilities=tuple(
            availability
            for availability in original.availabilities
            if availability.engineer_id in {engineer.id for engineer in engineers}
        ),
        tasks=(impossible,),
        travel_time_matrix=original.travel_time_matrix,
        travel_distance_matrix=original.travel_distance_matrix,
    )

    result = ICOOptimizer(ico_config=small_search_config()).optimize(problem)

    assert result.unassigned_task_ids == ("impossible",)
    assert (
        result.unassigned_reasons["impossible"].code
        == UnassignedReasonCode.MISSING_QUALIFICATION
    )


def test_ico_result_is_never_worse_than_its_baseline_seed() -> None:
    """Ограниченный ICO-поиск сохраняет стартовый допустимый baseline-план."""
    from backend.optimization import GreedyBaselineOptimizer

    problem = build_problem()
    baseline = GreedyBaselineOptimizer().optimize(problem)
    result = ICOOptimizer(ico_config=small_search_config()).optimize(problem)

    assert result.total_objective <= baseline.total_objective


def test_ico_optimizer_keeps_started_task_first_and_fixed() -> None:
    """Начатая заявка остаётся у текущего инженера и в начале маршрута."""
    original = build_problem()
    started = replace(
        original.tasks[0],
        status=TaskStatus.EN_ROUTE,
        current_engineer_id="e3",
    )
    problem = replace(original, tasks=(started, *original.tasks[1:]))

    result = ICOOptimizer(ico_config=small_search_config()).optimize(problem)

    assert result.routes["e3"].stops[0].task_id == started.id
    assert all(
        stop.task_id != started.id
        for engineer_id, route in result.routes.items()
        if engineer_id != "e3"
        for stop in route.stops
    )
