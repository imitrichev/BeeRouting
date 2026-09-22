"""Тесты импорта официального JSON-сценария."""

from collections import Counter
import json
from pathlib import Path

from backend.optimization import (
    InMemoryRoutingProvider,
    Skill,
    TaskStatus,
    VehicleType,
    load_control_dataset,
    load_json_scenario,
    load_json_scenario_data,
)
from backend.optimization.scripts.generate_dataset_json import (
    DEFAULT_MOSCOW_COORDINATES,
    NominatimGeocoder,
    _normalise_address,
    _replace_building_marker,
    _resolve_coordinates,
    generate_dataset,
)


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
    assert scenario.location_coordinates["office_start"] == (55.6638404, 37.6138686)


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


def test_all_dataset_statuses_are_normalized_in_backend() -> None:
    """Импортёр принимает статусы источника и приводит их к TaskStatus."""
    source_statuses = (
        ("Не отправлена", TaskStatus.NOT_SENT),
        ("Отправлена", TaskStatus.ASSIGNED),
        ("Назначена", TaskStatus.ASSIGNED),
        ("В пути", TaskStatus.EN_ROUTE),
        ("В работе", TaskStatus.IN_PROGRESS),
        ("Выполнена", TaskStatus.COMPLETED),
        ("Отменена", TaskStatus.CANCELLED),
        ("Просрочена", TaskStatus.OVERDUE),
    )
    payload = {
        "scenario": "status-test",
        "office_start_point": {"lat": 55.7, "lon": 37.6},
        "engineers": [
            {
                "engineer_id": "engineer-1",
                "name": "Инженер",
                "skills": ["local_works"],
                "vehicle_type": "car",
                "start_lat": 55.7,
                "start_lon": 37.6,
                "shift_start": "09:00",
                "shift_end": "18:00",
            }
        ],
        "jobs": [
            {
                "job_id": f"task-{index}",
                "lat": 55.7,
                "lon": 37.6,
                "skill_required": "local_works",
                "duration_min": 30,
                "window_start": "09:00",
                "window_end": "10:00",
                "priority": "normal",
                "required_vehicle": None,
                "reference_status": source_status,
                "reference_crew": "Инженер",
            }
            for index, (source_status, _) in enumerate(source_statuses)
        ],
    }

    scenario = load_json_scenario_data(payload)

    assert [task.status for task in scenario.tasks] == [
        expected_status for _, expected_status in source_statuses
    ]


def test_all_generated_datasets_with_unassigned_jobs_are_loadable() -> None:
    """Пустой reference_crew допустим у заявки со статусом «Не отправлена»."""
    source_root = Path(__file__).parents[3]

    scenarios = [
        load_json_scenario(source_root / "Югоцентр.json"),
        load_json_scenario(source_root / "Юго-восток.json"),
        load_json_scenario(source_root / "Восток.json"),
    ]

    assert all(scenario.tasks for scenario in scenarios)
    assert any(
        task.status == TaskStatus.NOT_SENT
        for scenario in scenarios
        for task in scenario.tasks
    )


def test_generator_uses_synthetic_ids_and_time_norms(tmp_path: Path) -> None:
    """Генератор берёт заявки из синтетического CSV и длительность из ТЗ."""
    output_path = tmp_path / "Югоцентр.json"
    source_root = Path(__file__).parents[3]
    generate_dataset(
        source_root / "Югоцентр Синтетические данные.csv",
        output_path,
        source_root / "Югоцентр Контрольное распределение..csv",
        source_root / "engineers.csv",
        geocoder=lambda _address: (55.70000123, 37.64000456),
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


def test_generator_normalizes_apartment_before_geocoding(tmp_path: Path) -> None:
    """Геокодер получает адрес дома без квартирной части."""
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
        geocoder=fake_geocoder,
    )
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["office_start_point"]["lat"] == 55.75581234
    assert calls
    assert all("кв." not in address for address in calls)
    assert result["jobs"][0]["lat"] == 55.75581234


def test_engineers_csv_contains_start_address_instead_of_coordinates() -> None:
    """Справочник хранит адрес старта, а не готовые координаты."""
    source_root = Path(__file__).parents[3]
    rows = source_root.joinpath("engineers.csv").read_text(encoding="utf-8").splitlines()
    header = rows[0].split(";")
    assert "start_address" in header
    assert "start_lat" not in header
    assert "start_lon" not in header


def test_address_normalization_does_not_truncate_moscow() -> None:
    """Нормализация удаляет квартиру, но сохраняет название города."""
    assert _normalise_address("Город Москва, ул. Примерная, д. 9") == (
        "город москва, ул. примерная, д. 9"
    )
    assert _normalise_address("Город Москва, ул. Примерная, д. 9, кв. 47") == (
        "город москва, ул. примерная, д. 9"
    )


def test_building_marker_is_normalized_to_k() -> None:
    """Форму с «к» можно построить только для резервного поиска."""
    assert _replace_building_marker("Москва, д. 1с1") == "Москва, д. 1 к 1"
    assert _replace_building_marker("Москва, д. 12 стр. 2") == "Москва, д. 12 к 2"
    assert _replace_building_marker("Москва, д. 9б стр. 1") == "Москва, д. 9б к 1"
    assert _normalise_address("Москва, д. 1с1") == "москва, д. 1с1"


def test_nominatim_delay_depends_on_endpoint(tmp_path: Path) -> None:
    """Локальный сервер работает без паузы, публичный — с паузой 1,1 с."""
    local = NominatimGeocoder(
        cache_path=tmp_path / "local.json",
        endpoint="http://127.0.0.1:8080/search",
    )
    remote = NominatimGeocoder(
        cache_path=tmp_path / "remote.json",
        endpoint="https://nominatim.openstreetmap.org/search",
    )

    assert local.is_local
    assert local.min_interval_seconds == 0
    assert not remote.is_local
    assert remote.min_interval_seconds == 1.1


def test_unresolved_address_gets_visible_default(capsys) -> None:
    """Ошибка адреса не останавливает dataset и явно указывает субъект."""
    def missing(_address: str) -> tuple[float, float]:
        raise ValueError("не найден")

    coordinates = _resolve_coordinates("Плохой адрес", missing, "заявка J1")

    assert coordinates == DEFAULT_MOSCOW_COORDINATES
    assert "заявка J1" in capsys.readouterr().out
