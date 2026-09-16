"""Тесты импорта официального JSON-сценария."""

from pathlib import Path

from backend.optimization import (
    InMemoryRoutingProvider,
    Skill,
    VehicleType,
    load_control_dataset,
    load_json_scenario,
)


JSON_PATH = Path(__file__).parents[3] / "yugo_center.json"
CONTROL_CSV_PATH = Path(__file__).parents[3] / "yugo_center.csv"


def test_yugo_center_json_loads_into_domain_models() -> None:
    """JSON преобразуется в инженеров, смены, заявки и координаты."""
    scenario = load_json_scenario(JSON_PATH)

    assert scenario.scenario_name == "yugo_tsentr_day"
    assert len(scenario.engineers) == 11
    assert len(scenario.availabilities) == 11
    assert len(scenario.tasks) == 56
    assert scenario.engineers[0].start_location_id == "office_start"
    assert scenario.tasks[0].required_skills == frozenset({Skill.CONNECTION_AND_UPSELL})
    assert scenario.engineers[0].vehicle_type == VehicleType.CAR
    assert scenario.tasks[0].duration_minutes == 45
    assert scenario.tasks[0].window_start == "18:00"
    assert scenario.location_coordinates["office_start"] == (55.617, 37.61)


def test_imported_scenario_builds_problem_from_routing_provider() -> None:
    """Импортёр получает обе матрицы извне и создаёт OptimizationProblem."""
    scenario = load_json_scenario(JSON_PATH)
    location_ids = tuple(scenario.location_coordinates)
    provider = InMemoryRoutingProvider(
        {
            source: {
                destination: 0 if source == destination else 1
                for destination in location_ids
            }
            for source in location_ids
        },
        {
            source: {
                destination: 0.0 if source == destination else 1.0
                for destination in location_ids
            }
            for source in location_ids
        },
    )

    problem = scenario.to_problem(provider)

    assert problem.travel_time_matrix["office_start"][scenario.tasks[0].location_id] == 1
    assert problem.travel_distance_matrix["office_start"][scenario.tasks[0].location_id] == 1.0


def test_control_csv_matches_json_and_preserves_cancelled_assignments() -> None:
    """Контрольный CSV сверяется с JSON, включая статус отменённых заявок."""
    scenario = load_json_scenario(JSON_PATH)
    control = load_control_dataset(CONTROL_CSV_PATH, scenario)

    assert control.consistent
    assert len(control.assignments) == len(scenario.tasks)
    cancelled_ids = {
        task.id for task in scenario.tasks if task.status.value == "CANCELLED"
    }
    assert cancelled_ids
    assert cancelled_ids.issubset({assignment.task_id for assignment in control.assignments})
