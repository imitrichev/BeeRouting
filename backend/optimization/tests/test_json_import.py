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
CONTROL_CSV_PATH = Path(__file__).parents[3] / "Югоцентр Контрольное распределение.csv"


def test_each_region_uses_its_own_office_as_engineer_start() -> None:
    """Офис и старты инженеров загружаются из своего районного JSON."""
    root = Path(__file__).parents[3]
    for filename in ("Восток.json", "Юго-восток.json", "Югоцентр.json"):
        payload = json.loads((root / filename).read_text(encoding="utf-8"))
        scenario = load_json_scenario_data(payload)
        office = payload["office_start_point"]
        expected = (office["lat"], office["lon"])
        assert scenario.location_coordinates["office_start"] == expected
        expected_starts = {
            engineer["engineer_id"]: (engineer["start_lat"], engineer["start_lon"])
            for engineer in payload["engineers"]
        }
        assert all(
            (engineer.start_latitude, engineer.start_longitude)
            == expected_starts[engineer.id]
            for engineer in scenario.engineers
        )


def test_engineers_can_start_from_different_locations_than_office() -> None:
    """Офис и индивидуальные точки старта являются разными локациями."""
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    payload["engineers"][0]["start_lat"] = 55.71
    payload["engineers"][0]["start_lon"] = 37.61
    payload["engineers"][1]["start_lat"] = 55.72
    payload["engineers"][1]["start_lon"] = 37.62

    scenario = load_json_scenario_data(payload)

    first, second = scenario.engineers[:2]
    office = payload["office_start_point"]
    assert scenario.location_coordinates["office_start"] == (
        office["lat"],
        office["lon"],
    )
    assert scenario.location_coordinates[first.start_location_id] == (55.71, 37.61)
    assert scenario.location_coordinates[second.start_location_id] == (55.72, 37.62)
    assert first.start_location_id != second.start_location_id


def test_started_tasks_have_known_current_engineers_in_all_regions() -> None:
    """EN_ROUTE/IN_PROGRESS всегда ссылаются на инженера своего района."""
    root = Path(__file__).parents[3]
    for filename in ("Восток.json", "Юго-восток.json", "Югоцентр.json"):
        scenario = load_json_scenario(root / filename)
        engineer_ids = {engineer.id for engineer in scenario.engineers}
        started = [
            task for task in scenario.tasks
            if task.status in {TaskStatus.EN_ROUTE, TaskStatus.IN_PROGRESS}
        ]
        assert started
        assert all(task.current_engineer_id in engineer_ids for task in started)


def test_yugo_center_json_loads_into_domain_models() -> None:
    """JSON преобразуется в инженеров, смены, заявки и координаты."""
    scenario = load_json_scenario(JSON_PATH)

    assert scenario.scenario_name == "yugo_tsentr_day"
    assert len(scenario.engineers) == 11
    assert len(scenario.availabilities) == 11
    assert len(scenario.tasks) == 56
    assert scenario.engineers[0].start_location_id == "engineer_start:yugo_tsentr-E01"
    assert scenario.tasks[0].required_skills == frozenset({Skill.CONNECTION_AND_UPSELL})
    assert scenario.engineers[0].vehicle_type == VehicleType.CAR
    assert scenario.tasks[0].duration_minutes == 70
    assert scenario.tasks[0].window_start == "18:00"
    assert sorted(scenario.reference_sequence_by_task.values()) == list(
        range(1, len(scenario.tasks) + 1)
    )
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    office = payload["office_start_point"]
    assert scenario.location_coordinates["office_start"] == (
        office["lat"],
        office["lon"],
    )


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

    start_id = scenario.engineers[0].start_location_id
    assert problem.travel_time_matrix[start_id][scenario.tasks[0].location_id] == 1
    assert problem.travel_distance_matrix[start_id][scenario.tasks[0].location_id] == 1.0


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
        source_root / "Югоцентр Контрольное распределение.csv",
        source_root / "engineers.csv",
        geocoder=lambda _address: (55.70000123, 37.64000456),
    )
    scenario = load_json_scenario(output_path)

    assert scenario.tasks[0].id == "yugo_tsentr-J32840"
    assert scenario.tasks[0].duration_minutes == 70
    assert Counter(task.duration_minutes for task in scenario.tasks) == Counter(
        {70: 28, 30: 25, 20: 2, 80: 1}
    )
    assert scenario.control_request_id_by_task[scenario.tasks[0].id] == "32840"
    assert scenario.engineers[1].vehicle_type == VehicleType.PUBLIC_TRANSPORT
    assert Skill.LOCAL_WORKS in scenario.engineers[1].qualifications
    assert scenario.engineers[0].available_router_count >= 0
    assert any(task.required_router_count > 0 for task in scenario.tasks)
    assert sorted(scenario.reference_sequence_by_task.values()) == list(
        range(1, len(scenario.tasks) + 1)
    )


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


def test_engineers_csv_contains_start_address_and_coordinates() -> None:
    """Справочник хранит проверенный адрес и координаты старта инженеров."""
    source_root = Path(__file__).parents[3]
    rows = source_root.joinpath("engineers.csv").read_text(encoding="utf-8").splitlines()
    header = rows[0].split(";")
    assert "start_address" in header
    assert "start_lat" in header
    assert "start_lon" in header
    assert "available_router_count" in header
    territory_index = header.index("territory_code")
    engineer_index = header.index("engineer_id")
    lat_index = header.index("start_lat")
    lon_index = header.index("start_lon")
    expected = {
        "vostok": (55.7022013, 37.7739593),
        "yugo_vostok": (55.5868278, 37.6654561),
        "yugo_tsentr": (55.6638404, 37.6138686),
    }
    # Удалённые бригады начинают день в обслуживаемом городе, а не в
    # московском офисе района. Это предусмотрено доменной моделью инженера.
    individual_starts = {
        "yugo_vostok-E01": (54.8858274, 38.0821597),
        "yugo_vostok-E09": (54.8415134, 38.2407727),
    }
    for raw_row in rows[1:]:
        row = raw_row.split(";")
        expected_start = individual_starts.get(
            row[engineer_index], expected[row[territory_index]]
        )
        assert (float(row[lat_index]), float(row[lon_index])) == expected_start


def test_address_normalization_does_not_truncate_moscow() -> None:
    """Нормализация удаляет квартиру и лишние служебные маркеры города."""
    assert _normalise_address("Город Москва, ул. Примерная, д. 9") == (
        "москва, ул. примерная, д. 9"
    )
    assert _normalise_address("Город Москва, ул. Примерная, д. 9, кв. 47") == (
        "москва, ул. примерная, д. 9"
    )
    assert _normalise_address("г.Город Москва, ул. Примерная, д. 9") == (
        "москва, ул. примерная, д. 9"
    )
    assert _normalise_address("Москва, ул. Примерная, д. 9") == (
        "москва, ул. примерная, д. 9"
    )


def test_query_variants_preserve_explicit_city() -> None:
    """Геокодер не приписывает Москву адресу из Домодедова."""
    variants = NominatimGeocoder._query_variants(
        "Домодедово, ул.1-я Коммунистическая, д. 39"
    )

    assert "домодедово, 1-я коммунистическая улица, 39" in variants
    assert all(not variant.startswith("москва") for variant in variants)


def test_building_marker_is_normalized_to_k() -> None:
    """Форму с «к» можно построить только для резервного поиска."""
    assert _replace_building_marker("Москва, д. 1с1") == "Москва, д. 1 к 1"
    assert _replace_building_marker("Москва, д. 12 стр. 2") == "Москва, д. 12 к 2"
    assert _replace_building_marker("Москва, д. 9б стр. 1") == "Москва, д. 9б к 1"
    assert _replace_building_marker("Домодедово, ул. Гагарина, д. 55/2") == (
        "Домодедово, ул. Гагарина, д. 55 к 2"
    )
    assert _normalise_address("Москва, д. 1с1") == "москва, д. 1с1"


def test_nominatim_accepts_only_results_with_house_or_building_number() -> None:
    """Площадь без номера здания не принимается как найденный дом."""
    assert NominatimGeocoder._is_precise_result(
        {"addresstype": "square", "address": {"name": "площадь Гагарина"}}
    ) is False
    assert NominatimGeocoder._is_precise_result(
        {"addresstype": "building", "address": {"house_number": "55к2"}}
    ) is True
    assert NominatimGeocoder._is_precise_result(
        {"addresstype": "building", "address": {"building": "55к2"}}
    ) is True


def test_nominatim_tries_next_variant_after_result_without_house_number(tmp_path: Path) -> None:
    """Результат уровня площади отклоняется, следующий запрос продолжается."""
    geocoder = NominatimGeocoder(
        cache_path=tmp_path / "nominatim.json",
        endpoint="http://127.0.0.1:8080/search",
    )
    calls: list[str] = []

    def fake_request(query: str, original: str) -> list[dict[str, object]]:
        calls.append(query)
        if len(calls) == 1:
            return [{
                "lat": "55.60",
                "lon": "37.70",
                "addresstype": "square",
                "address": {"name": "площадь Гагарина"},
            }]
        return [{
            "lat": "55.602",
            "lon": "37.665",
            "addresstype": "building",
            "address": {"house_number": "55к2"},
        }]

    geocoder._request = fake_request  # type: ignore[method-assign]
    coordinates = geocoder("Домодедово, ул. Гагарина, д. 55/2")

    assert coordinates == (55.602, 37.665)
    assert len(calls) >= 2


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


def test_nominatim_selects_result_nearest_to_office() -> None:
    """Одноимённый дом выбирается по близости к офису обслуживаемого района."""
    tagansky = {"lat": "55.737", "lon": "37.674"}
    shcherbinka = {"lat": "55.510", "lon": "37.570"}

    selected = NominatimGeocoder._nearest_result(
        [shcherbinka, tagansky],
        (55.74, 37.66),
    )

    assert selected is tagansky


def test_query_variants_keep_intermediate_locality() -> None:
    """Название Щербинки не удаляется из адреса между Москвой и улицей."""
    variants = NominatimGeocoder._query_variants(
        "Москва, Щербинка, ул. Талалихина, д. 16"
    )

    assert any("щербинка" in variant for variant in variants)


def test_query_variants_try_exact_house_fallbacks_before_street() -> None:
    """Геокодер умеет исправлять распространённые формы адресов из CSV."""
    cases = {
        "Город Москва, ул.Машкова, д. 13 стр. 1": "москва, машкова улица, 13с1",
        "Город Москва, ул.Дубининская, д. 59 к 2": "москва, дубининская улица, 59",
        "Город Москва, б-р.Смоленский, д. 17 стр. 1": "москва, смоленский бульвар, 17с1",
        "МО, г. Кашира Кржижановского ул. д. 5/2": "кашира, улица кржижановского, 5к2",
        (
            "обл.Московская область, г.Домодедово, пгт.Востряково-1, "
            "ул.Жуковского, д. 14/18"
        ): "домодедово, улица жуковского, 14/18",
        "Домодедово, проезд.Советский 1-й, д. 1А": (
            "домодедово, 1-й советский проезд, 1а"
        ),
    }

    for address, expected in cases.items():
        assert expected in NominatimGeocoder._query_variants(address)


def test_unresolved_address_gets_visible_default(capsys) -> None:
    """Ошибка адреса не останавливает dataset и явно указывает субъект."""
    def missing(_address: str) -> tuple[float, float]:
        raise ValueError("не найден")

    coordinates = _resolve_coordinates("Плохой адрес", missing, "заявка J1")

    assert coordinates == DEFAULT_MOSCOW_COORDINATES
    assert "заявка J1" in capsys.readouterr().out
