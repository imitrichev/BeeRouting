"""Тесты импорта официального JSON-сценария."""

import csv
from collections import Counter
import json
from pathlib import Path

from backend.optimization import (
    InMemoryRoutingProvider,
    Skill,
    VehicleType,
    load_control_dataset,
    load_json_scenario,
)
from backend.optimization.scripts.generate_dataset_json import generate_dataset


JSON_PATH = Path(__file__).parents[3] / "Югоцентр.json"
CONTROL_CSV_PATH = Path(__file__).parents[3] / "Югоцентр Контрольное распределение..csv"


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
    assert scenario.tasks[0].duration_minutes == 70
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


def test_generator_uses_synthetic_ids_and_time_norms(tmp_path: Path) -> None:
    """Генератор берёт заявки из синтетического CSV и длительность из ТЗ."""
    output_path = tmp_path / "Югоцентр.json"
    source_root = Path(__file__).parents[3]
    old_payload = json.loads((source_root / "yugo_center.json").read_text(encoding="utf-8"))
    coordinates_by_address = {
        job["address"]: (job["lat"], job["lon"])
        for job in old_payload["jobs"]
    }
    synthetic_rows = []
    with (source_root / "Югоцентр Синтетические данные.csv").open(encoding="cp1251", newline="") as csv_file:
        synthetic_rows = list(csv.DictReader(csv_file, delimiter=";"))
    address_path = tmp_path / "address.csv"
    with address_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["address", "latitude", "longitude"], delimiter=";")
        writer.writeheader()
        writer.writerow({"address": "г.Москва проезд Симферопольский, д.7", "latitude": "55.61712345", "longitude": "37.61098765"})
        for row in synthetic_rows:
            if row.get("Заявка", "").isdigit():
                lat, lon = coordinates_by_address[row["Адрес"]]
                writer.writerow({"address": row["Адрес"], "latitude": f"{lat:.8f}", "longitude": f"{lon:.8f}"})

    generate_dataset(
        source_root / "Югоцентр Синтетические данные.csv",
        output_path,
        source_root / "Югоцентр Контрольное распределение..csv",
        source_root / "engineers.csv",
        address_path,
    )
    scenario = load_json_scenario(output_path)

    assert scenario.tasks[0].id == "yugo_tsentr-J32840"
    assert scenario.tasks[0].duration_minutes == 70
    assert Counter(task.duration_minutes for task in scenario.tasks) == Counter(
        {70: 28, 30: 25, 20: 2, 80: 1}
    )
    assert scenario.control_request_id_by_task[scenario.tasks[0].id] == "305894566"
    assert scenario.engineers[1].vehicle_type == VehicleType.WALK
    assert Skill.LOCAL_WORKS in scenario.engineers[1].qualifications


def test_generator_uses_geocoder_only_for_missing_house(tmp_path: Path) -> None:
    """Квартира отбрасывается, а геокодер вызывается только для отсутствующего дома."""
    address_path = tmp_path / "address.csv"
    address_path.write_text(
        "address;latitude;longitude\n"
        "г.Москва проезд Симферопольский, д.7;55.60000123;37.60000456\n"
        "Город Москва, проезд.3-й Павелецкий, д. 9;55.70000123;37.64000456\n",
        encoding="utf-8",
    )
    source_root = Path(__file__).parents[3]
    calls: list[str] = []

    def fake_geocoder(address: str) -> tuple[float, float]:
        calls.append(address)
        return 55.75581234, 37.61769876

    output_path = tmp_path / "generated.json"
    generate_dataset(
        source_root / "Югоцентр Синтетические данные.csv",
        output_path,
        control_path=tmp_path / "missing-control.csv",
        engineers_path=source_root / "engineers.csv",
        address_path=address_path,
        geocoder=fake_geocoder,
    )
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["office_start_point"]["lat"] == 55.60000123
    assert calls  # остальные дома отсутствуют в маленьком тестовом справочнике
    assert all("кв." not in address for address in calls)
    assert result["jobs"][0]["lat"] == 55.70000123
