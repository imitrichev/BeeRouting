"""Тесты доменной модели и OR-Tools solver."""

import pytest

from backend.optimization import (
    Engineer,
    EngineerAvailability,
    EquipmentResource,
    OptimizationProblem,
    OptimizerConfig,
    ORToolsOptimizer,
    Priority,
    Skill,
    Task,
    UnassignedReasonCode,
    VehicleResource,
    VehicleType,
)


def full_matrix(locations: tuple[str, ...], default: int = 10) -> dict[str, dict[str, int]]:
    """Создаёт простую детерминированную матрицу времени в минутах."""
    return {
        source: {
            destination: 0 if source == destination else default
            for destination in locations
        }
        for source in locations
    }


def full_distance_matrix(
    locations: tuple[str, ...], default: float = 1.0
) -> dict[str, dict[str, float]]:
    """Создаёт простую детерминированную матрицу расстояний в километрах."""
    return {
        source: {
            destination: 0.0 if source == destination else default
            for destination in locations
        }
        for source in locations
    }


def make_engineer(
    engineer_id: str = "e1",
    skills: frozenset[Skill] | None = None,
    vehicle_type: VehicleType = VehicleType.CAR,
    start_location_id: str = "base",
    available_equipment: frozenset[str] = frozenset(),
    **kwargs: object,
) -> Engineer:
    """Создаёт инженера для теста."""
    return Engineer(
        id=engineer_id,
        name=engineer_id,
        qualifications=(
            frozenset({Skill.LOCAL_WORKS}) if skills is None else skills
        ),
        start_location_id=start_location_id,
        vehicle_type=vehicle_type,
        available_equipment=available_equipment,
        **kwargs,
    )


def make_task(
    task_id: str = "t1",
    skill: Skill = Skill.LOCAL_WORKS,
    location_id: str = "customer",
    duration_minutes: int = 10,
    window_start: str = "08:00",
    window_end: str = "17:00",
    required_vehicle_type: VehicleType | None = None,
    required_equipment: frozenset[str] = frozenset(),
    priority: Priority = Priority.NORMAL,
) -> Task:
    """Создаёт заявку с одним официальным навыком."""
    return Task(
        id=task_id,
        location_id=location_id,
        required_skills=frozenset({skill}),
        duration_minutes=duration_minutes,
        window_start=window_start,
        window_end=window_end,
        required_vehicle_type=required_vehicle_type,
        required_equipment=required_equipment,
        priority=priority,
    )


def build_problem() -> OptimizationProblem:
    """Создаёт базовый сценарий с тремя инженерами и пятью заявками."""
    engineers = (
        make_engineer("e1", frozenset({Skill.LOCAL_WORKS, Skill.CONNECTION_AND_UPSELL})),
        make_engineer("e2", frozenset({Skill.EMERGENCY_WORKS})),
        make_engineer("e3", frozenset({Skill.LOCAL_WORKS, Skill.EMERGENCY_WORKS})),
    )
    tasks = (
        make_task("t1", Skill.LOCAL_WORKS, "customer-1", 30),
        make_task("t2", Skill.EMERGENCY_WORKS, "customer-2", 45),
        make_task("t3", Skill.CONNECTION_AND_UPSELL, "customer-3", 20),
        make_task("t4", Skill.LOCAL_WORKS, "customer-4", 30),
        make_task("t5", Skill.EMERGENCY_WORKS, "customer-5", 15),
    )
    locations = (
        "base",
        "customer-1",
        "customer-2",
        "customer-3",
        "customer-4",
        "customer-5",
    )
    matrix = full_matrix(locations)
    return OptimizationProblem(
        engineers=engineers,
        availabilities=tuple(
            EngineerAvailability(engineer.id, "08:00", "17:00")
            for engineer in engineers
        ),
        tasks=tasks,
        travel_time_matrix=matrix,
        travel_distance_matrix=full_distance_matrix(locations),
    )


def test_solver_assigns_all_tasks_and_returns_minutes_and_hhmm() -> None:
    """Все заявки назначаются, а результат использует минуты и HH:MM."""
    result = ORToolsOptimizer().optimize(build_problem())

    assigned = {
        stop.task_id
        for route in result.routes.values()
        for stop in route.stops
    }
    assert assigned == {"t1", "t2", "t3", "t4", "t5"}
    assert result.unassigned_task_ids == ()
    assert result.total_travel_time >= 0
    assert any(len(route.stops) > 1 for route in result.routes.values())
    for route in result.routes.values():
        assert route.total_service_minutes == sum(
            next(task for task in build_problem().tasks if task.id == stop.task_id).duration_minutes
            for stop in route.stops
        )
        for stop in route.stops:
            assert len(stop.arrival_time.split(":")) == 2
            assert len(stop.service_start_time.split(":")) == 2


def test_skill_catalog_accepts_three_engineer_skills_and_one_task_skill() -> None:
    """Справочник содержит три навыка, инженер может иметь все три."""
    engineer = make_engineer(
        skills=frozenset({
            Skill.LOCAL_WORKS,
            Skill.CONNECTION_AND_UPSELL,
            Skill.EMERGENCY_WORKS,
        })
    )
    task = make_task(skill=Skill.EMERGENCY_WORKS)
    assert engineer.qualifications == frozenset(Skill)
    assert task.required_skills == frozenset({Skill.EMERGENCY_WORKS})


@pytest.mark.parametrize("skill", list(Skill))
def test_each_skill_can_be_required_by_a_task(skill: Skill) -> None:
    """Каждый из трёх навыков принимается в заявке."""
    task = make_task(skill=skill)
    assert task.required_skills == frozenset({skill})


def test_skill_cardinality_is_validated() -> None:
    """Инженер имеет от одного до трёх навыков, заявка — ровно один."""
    with pytest.raises(ValueError):
        make_engineer(skills=frozenset())
    with pytest.raises(ValueError):
        Task(
            "t1", "customer", frozenset({Skill.LOCAL_WORKS, Skill.EMERGENCY_WORKS}),
            10, window_start="08:00", window_end="17:00",
        )


@pytest.mark.parametrize("vehicle_type", list(VehicleType))
def test_all_four_vehicle_types_are_supported(vehicle_type: VehicleType) -> None:
    """Каждый из четырёх типов транспорта совместим с таким же требованием."""
    engineer = make_engineer(vehicle_type=vehicle_type)
    task = make_task(required_vehicle_type=vehicle_type)
    problem = OptimizationProblem(
        engineers=(engineer,),
        availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
        tasks=(task,),
        travel_time_matrix={
            "base": {"base": 0, "customer": 1},
            "customer": {"base": 1, "customer": 0},
        },
        travel_distance_matrix={
            "base": {"base": 0.0, "customer": 2.0},
            "customer": {"base": 2.0, "customer": 0.0},
        },
    )
    assert ORToolsOptimizer().optimize(problem).unassigned_task_ids == ()


def test_optional_vehicle_requirement_and_incompatible_vehicle() -> None:
    """Без требования транспорт не проверяется, при требовании тип обязан совпасть."""
    engineer = make_engineer(vehicle_type=VehicleType.WALK)
    optional_task = make_task()
    required_task = make_task(
        "t2", required_vehicle_type=VehicleType.CAR, location_id="customer-2"
    )
    problem = OptimizationProblem(
        engineers=(engineer,),
        availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
        tasks=(optional_task, required_task),
        travel_time_matrix=full_matrix(("base", "customer", "customer-2"), 1),
        travel_distance_matrix=full_distance_matrix(
            ("base", "customer", "customer-2"), 1.0
        ),
    )
    result = ORToolsOptimizer().optimize(problem)
    assert result.routes["e1"].stops[0].task_id == "t1"
    assert result.unassigned_task_ids == ("t2",)
    assert result.unassigned_reasons["t2"].code == UnassignedReasonCode.MISSING_VEHICLE_TYPE


def test_task_without_equipment_requirements_is_assignable() -> None:
    """Пустое required_equipment не ограничивает назначение."""
    result = ORToolsOptimizer().optimize(
        OptimizationProblem(
            engineers=(make_engineer(),),
            availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
            tasks=(make_task(),),
            travel_time_matrix=full_matrix(("base", "customer"), 1),
            travel_distance_matrix=full_distance_matrix(("base", "customer")),
        )
    )

    assert result.assigned_task_count == 1
    assert result.unassigned_task_ids == ()


def test_task_with_all_available_equipment_is_assignable() -> None:
    """Заявка назначается при полном покрытии required_equipment."""
    engineer = make_engineer(
        available_equipment=frozenset({"meter", "router"}),
    )
    task = make_task(required_equipment=frozenset({"meter", "router"}))
    result = ORToolsOptimizer().optimize(
        OptimizationProblem(
            engineers=(engineer,),
            availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
            tasks=(task,),
            travel_time_matrix=full_matrix(("base", "customer"), 1),
            travel_distance_matrix=full_distance_matrix(("base", "customer")),
        )
    )

    assert result.unassigned_task_ids == ()


def test_missing_one_equipment_item_is_a_hard_constraint() -> None:
    """Отсутствие одного элемента оборудования запрещает назначение."""
    engineer = make_engineer(available_equipment=frozenset({"meter"}))
    task = make_task(required_equipment=frozenset({"meter", "router"}))
    result = ORToolsOptimizer().optimize(
        OptimizationProblem(
            engineers=(engineer,),
            availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
            tasks=(task,),
            travel_time_matrix=full_matrix(("base", "customer"), 1),
            travel_distance_matrix=full_distance_matrix(("base", "customer")),
        )
    )

    assert result.unassigned_task_ids == ("t1",)
    assert result.unassigned_reasons["t1"].code == UnassignedReasonCode.MISSING_EQUIPMENT


def test_equipment_vehicle_and_skill_constraints_work_together() -> None:
    """Назначение требует одновременного совпадения навыка, транспорта и оборудования."""
    engineer = make_engineer(
        skills=frozenset({Skill.CONNECTION_AND_UPSELL}),
        vehicle_type=VehicleType.BICYCLE,
        available_equipment=frozenset({"router"}),
    )
    task = make_task(
        skill=Skill.CONNECTION_AND_UPSELL,
        required_vehicle_type=VehicleType.BICYCLE,
        required_equipment=frozenset({"router"}),
    )
    result = ORToolsOptimizer().optimize(
        OptimizationProblem(
            engineers=(engineer,),
            availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
            tasks=(task,),
            travel_time_matrix=full_matrix(("base", "customer"), 1),
            travel_distance_matrix=full_distance_matrix(("base", "customer")),
        )
    )

    assert result.assigned_task_count == 1


def test_equipment_and_separate_vehicle_resource_are_supported() -> None:
    """Закреплённые ресурсы участвуют в проверке совместимости."""
    engineer = make_engineer(
        equipment_resource_ids=frozenset({"meter-1"}),
        vehicle_type=VehicleType.BICYCLE,
        vehicle_resource_id="bike-1",
    )
    problem = OptimizationProblem(
        engineers=(engineer,),
        availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
        tasks=(make_task(required_equipment=frozenset({"meter"}), required_vehicle_type=VehicleType.BICYCLE),),
        travel_time_matrix={
            "base": {"base": 0, "customer": 1},
            "customer": {"base": 1, "customer": 0},
        },
        travel_distance_matrix={
            "base": {"base": 0.0, "customer": 2.0},
            "customer": {"base": 2.0, "customer": 0.0},
        },
        equipment_resources=(EquipmentResource("meter-1", "meter"),),
        vehicle_resources=(VehicleResource("bike-1", VehicleType.BICYCLE),),
    )
    assert ORToolsOptimizer().optimize(problem).unassigned_task_ids == ()


def test_solver_waits_until_hard_visit_window() -> None:
    """Ранний приезд допускается, но начало работы ждёт открытия окна."""
    problem = OptimizationProblem(
        engineers=(make_engineer(),),
        availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
        tasks=(make_task(window_start="10:00", window_end="11:00", duration_minutes=30),),
        travel_time_matrix={
            "base": {"base": 0, "customer": 10},
            "customer": {"base": 10, "customer": 0},
        },
        travel_distance_matrix={
            "base": {"base": 0.0, "customer": 2.0},
            "customer": {"base": 2.0, "customer": 0.0},
        },
    )
    stop = ORToolsOptimizer().optimize(problem).routes["e1"].stops[0]
    assert stop.arrival_time == "08:10"
    assert stop.service_start_time == "10:00"
    assert stop.service_end_time == "10:30"
    assert stop.travel_time_from_previous == 10


def test_visit_window_is_hard_constraint() -> None:
    """Заявка с недостижимым окном остаётся неназначенной."""
    problem = OptimizationProblem(
        engineers=(make_engineer(),),
        availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
        tasks=(make_task(window_start="08:00", window_end="08:05"),),
        travel_time_matrix={
            "base": {"base": 0, "customer": 10},
            "customer": {"base": 10, "customer": 0},
        },
        travel_distance_matrix={
            "base": {"base": 0.0, "customer": 2.0},
            "customer": {"base": 2.0, "customer": 0.0},
        },
    )
    result = ORToolsOptimizer().optimize(problem)
    assert result.unassigned_task_ids == ("t1",)
    assert result.unassigned_reasons["t1"].code == UnassignedReasonCode.IMPOSSIBLE_TIME_WINDOW


def test_engineer_shift_is_hard_constraint() -> None:
    """Работа, которая не завершается в смену, запрещает назначение."""
    problem = OptimizationProblem(
        engineers=(make_engineer(),),
        availabilities=(EngineerAvailability("e1", "08:00", "08:20"),),
        tasks=(make_task(duration_minutes=15),),
        travel_time_matrix={
            "base": {"base": 0, "customer": 10},
            "customer": {"base": 10, "customer": 0},
        },
        travel_distance_matrix={
            "base": {"base": 0.0, "customer": 2.0},
            "customer": {"base": 2.0, "customer": 0.0},
        },
    )
    result = ORToolsOptimizer().optimize(problem)
    assert result.unassigned_task_ids == ("t1",)
    assert result.unassigned_reasons["t1"].code == UnassignedReasonCode.OUTSIDE_WORKING_HOURS


def test_one_engineer_can_receive_multiple_tasks() -> None:
    """Один инженер может выполнить несколько заявок в одном маршруте."""
    problem = OptimizationProblem(
        engineers=(make_engineer(),),
        availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
        tasks=(
            make_task("t1", location_id="customer-1", duration_minutes=10),
            make_task("t2", location_id="customer-2", duration_minutes=20),
        ),
        travel_time_matrix=full_matrix(("base", "customer-1", "customer-2"), 5),
        travel_distance_matrix=full_distance_matrix(
            ("base", "customer-1", "customer-2"), 3.0
        ),
    )
    route = ORToolsOptimizer().optimize(problem).routes["e1"]
    assert len(route.stops) == 2
    assert route.total_service_minutes == 30
    assert route.stops[1].arrival_time >= route.stops[0].service_end_time


def test_route_does_not_include_return_to_start() -> None:
    """Пробег заканчивается на последней заявке, без обратной дуги к базе."""
    problem = OptimizationProblem(
        engineers=(make_engineer(),),
        availabilities=(EngineerAvailability("e1", "08:00", "08:16"),),
        tasks=(make_task(duration_minutes=5),),
        travel_time_matrix={
            "base": {"base": 0, "customer": 10},
            "customer": {"base": 10, "customer": 0},
        },
        travel_distance_matrix={
            "base": {"base": 0.0, "customer": 2.0},
            "customer": {"base": 2.0, "customer": 0.0},
        },
    )

    result = ORToolsOptimizer().optimize(problem)

    assert result.unassigned_task_ids == ()
    assert result.travel_time_by_engineer == {"e1": 10}
    assert result.distance_by_engineer == {"e1": 2.0}
    assert result.total_travel_time == 10
    assert result.total_distance == 2.0


def test_solver_prefers_smaller_distance_for_same_engineer_count() -> None:
    """При одинаковом числе инженеров OR-Tools выбирает короткий порядок."""
    problem = OptimizationProblem(
        engineers=(make_engineer(),),
        availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
        tasks=(
            make_task("t1", location_id="customer-1"),
            make_task("t2", location_id="customer-2"),
        ),
        travel_time_matrix={
            "base": {"base": 0, "customer-1": 1, "customer-2": 10},
            "customer-1": {"base": 10, "customer-1": 0, "customer-2": 1},
            "customer-2": {"base": 10, "customer-1": 10, "customer-2": 0},
        },
        travel_distance_matrix={
            "base": {"base": 0.0, "customer-1": 1.0, "customer-2": 10.0},
            "customer-1": {"base": 10.0, "customer-1": 0.0, "customer-2": 1.0},
            "customer-2": {"base": 10.0, "customer-1": 10.0, "customer-2": 0.0},
        },
    )

    result = ORToolsOptimizer().optimize(problem)

    assert [stop.task_id for stop in result.routes["e1"].stops] == ["t1", "t2"]
    assert result.used_engineers_count == 1
    assert result.total_distance == 2.0


def test_urgent_unassigned_penalty_is_greater_than_normal() -> None:
    """Потеря URGENT заявки дороже потери NORMAL заявки."""
    normal = make_task("normal", skill=Skill.EMERGENCY_WORKS)
    urgent = make_task(
        "urgent",
        skill=Skill.EMERGENCY_WORKS,
        location_id="customer-2",
        priority=Priority.URGENT,
    )
    locations = ("base", "customer", "customer-2")
    problem = OptimizationProblem(
        engineers=(make_engineer(),),
        availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
        tasks=(normal, urgent),
        travel_time_matrix=full_matrix(locations, 1),
        travel_distance_matrix=full_distance_matrix(locations, 1.0),
    )
    config = OptimizerConfig(unassigned_penalty=100)

    result = ORToolsOptimizer(config).optimize(problem)

    assert result.unassigned_task_ids == ("normal", "urgent")
    assert result.unassigned_penalty == 100 + 100 * config.urgent_unassigned_multiplier


def test_priority_is_part_of_the_domain_but_sla_is_absent() -> None:
    """Приоритет допускается, а задача не содержит SLA-поля."""
    task = make_task(priority=Priority.URGENT)
    problem = OptimizationProblem(
        engineers=(make_engineer(),),
        availabilities=(EngineerAvailability("e1", "08:00", "17:00"),),
        tasks=(task,),
        travel_time_matrix={
            "base": {"base": 0, "customer": 1},
            "customer": {"base": 1, "customer": 0},
        },
        travel_distance_matrix={
            "base": {"base": 0.0, "customer": 2.0},
            "customer": {"base": 2.0, "customer": 0.0},
        },
    )
    result = ORToolsOptimizer().optimize(problem)
    assert result.total_objective == (
        result.used_engineers_penalty
        + result.distance_penalty
        + result.travel_time_penalty
    )
