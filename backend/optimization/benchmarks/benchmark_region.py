"""Сравнение контрольного плана и выбранных solver'ов на dataset.

Baseline и OR-Tools запускаются всегда. Timefold и ICO-DE подключаются
флагами ``--include-timefold`` и ``--include-ico-de``.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import statistics
import time

from backend.optimization import (
    CoordinateRoutingProvider,
    GreedyBaselineOptimizer,
    ICOOptimizer,
    JsonScenario,
    ManualAssignmentPlanner,
    OptimizationProblem,
    OptimizationResult,
    OptimizerConfig,
    ICORoutingConfig,
    ORToolsOptimizer,
    OSRMRoutingProvider,
    create_osrm_provider_from_environment,
    RouteOptimizer,
    load_control_dataset_from_scenario,
    load_json_scenario,
    TimefoldOptimizer,
    TimefoldUnavailableError,
)


DEMO_TRAVEL_SPEED_KM_PER_HOUR = 30.0


def build_provider(
    scenario: JsonScenario,
    provider_name: str,
    osrm_timeout_seconds: float,
) -> CoordinateRoutingProvider | OSRMRoutingProvider:
    """Создаёт выбранный источник матриц времени и расстояния."""
    if provider_name == "coordinate":
        return CoordinateRoutingProvider(
            coordinates=scenario.location_coordinates,
            speed_km_per_hour=DEMO_TRAVEL_SPEED_KM_PER_HOUR,
        )
    return create_osrm_provider_from_environment(
        coordinates=scenario.location_coordinates,
        request_timeout_seconds=osrm_timeout_seconds,
    )


def _measure_optimizer(
    optimizer: RouteOptimizer,
    problem: OptimizationProblem,
    iterations: int,
) -> tuple[list[float], OptimizationResult]:
    """Прогревает реализацию и измеряет последующие запуски в секундах."""
    optimizer.optimize(problem)
    measurements: list[float] = []
    result: OptimizationResult | None = None
    for _ in range(iterations):
        started_at = time.perf_counter()
        result = optimizer.optimize(problem)
        measurements.append(time.perf_counter() - started_at)
    assert result is not None
    return measurements, result


def _measure_timefold(
    optimizer: TimefoldOptimizer,
    problem: OptimizationProblem,
    iterations: int,
) -> tuple[list[float], OptimizationResult]:
    """Измеряет Timefold без отдельного прогрева JVM.

    Для обычных Python-солверов выше есть прогревочный запуск. Timefold
    поднимает JVM и генерирует Java-классы constraint stream; повторный запуск
    JVM в том же процессе на текущем Python-адаптере ненадёжен и не даёт
    полезного сравнения. Поэтому первый запуск Timefold входит в измерение,
    а число последующих запусков задаётся тем же ``--iterations``.
    """
    measurements: list[float] = []
    result: OptimizationResult | None = None
    for _ in range(iterations):
        started_at = time.perf_counter()
        result = optimizer.optimize(problem)
        measurements.append(time.perf_counter() - started_at)
    assert result is not None
    return measurements, result


def _validate_status_contract(
    solver_name: str,
    problem: OptimizationProblem,
    result: OptimizationResult,
) -> None:
    """Проверяет, что benchmark не скрывает нарушение режима статусов.

    В полном режиме все заявки разрешены к перераспределению. В статусном
    режиме исторические заявки не должны попасть в новый маршрут, а начатые
    должны остаться у своего инженера и быть первым активным визитом.
    """
    route_by_task = {
        stop.task_id: engineer_id
        for engineer_id, route in result.routes.items()
        for stop in route.stops
    }
    if not problem.ignore_task_statuses:
        excluded_ids = {
            task.id
            for task in problem.tasks
            if task.status.value in {"CANCELLED", "COMPLETED"}
        }
        unexpected = sorted(excluded_ids & route_by_task.keys())
        if unexpected:
            raise RuntimeError(
                f"{solver_name}: исторические заявки попали в новый план: {unexpected}"
            )
        for task_id, engineer_id in problem.fixed_task_engineer_by_id.items():
            if route_by_task.get(task_id) != engineer_id:
                raise RuntimeError(
                    f"{solver_name}: заявка {task_id} нарушила закрепление "
                    f"за инженером {engineer_id}"
                )
        for task_id, engineer_id in problem.fixed_task_engineer_by_id.items():
            task = next(item for item in problem.tasks if item.id == task_id)
            if task.status.value not in {"EN_ROUTE", "IN_PROGRESS"}:
                continue
            route = result.routes[engineer_id]
            if not route.stops or route.stops[0].task_id != task_id:
                raise RuntimeError(
                    f"{solver_name}: начатая заявка {task_id} не является первым "
                    "визитом маршрута"
                )


def _format_value(value: float | int | None, decimals: int) -> str:
    """Форматирует значение таблицы или ставит прочерк для недопустимого плана."""
    if value is None:
        return "—"
    return f"{value:.{decimals}f}"


def _print_value_table(
    rows: list[
        tuple[
            str,
            float | int | None,
            float | int | None,
            float | int | None,
            float | int | None,
            float | int | None,
            int,
        ]
    ],
    *,
    include_ico: bool,
    include_timefold: bool,
) -> None:
    """Печатает значения всех вариантов без абсолютных изменений."""
    print()
    print(
        f"{'Метрика':<30} {'Контрольное':>16} {'Baseline':>16} "
        f"{'OR-Tools':>16}"
        + (f" {'ICO-DE':>16}" if include_ico else "")
        + (f" {'Timefold':>16}" if include_timefold else "")
    )
    print("-" * 100)
    for name, control, baseline, ortools, ico, timefold, decimals in rows:
        line = (
            f"{name:<30} {_format_value(control, decimals):>16} "
            f"{_format_value(baseline, decimals):>16} "
            f"{_format_value(ortools, decimals):>16}"
        )
        if include_ico:
            line += f" {_format_value(ico, decimals):>16}"
        if include_timefold:
            line += f" {_format_value(timefold, decimals):>16}"
        print(line)


def _percent_change(value: float | int | None, reference: float | int | None) -> str:
    """Возвращает только процентное изменение относительно reference."""
    if value is None or reference is None or reference == 0:
        return "н/д"
    return f"{abs((float(value) - float(reference)) / abs(float(reference)) * 100):.2f}%"


def _percent_phrase(
    metric: str,
    value: float | int | None,
    reference: float | int | None,
    solver_name: str,
    reference_name: str,
) -> str:
    """Формирует процентное описание без абсолютного изменения и знаков +/- ."""
    if value is None or reference is None or reference == 0:
        return f"{metric}: нет базы для сравнения {solver_name} с {reference_name}."
    change = float(value) - float(reference)
    relation = "больше" if change > 0 else "меньше" if change < 0 else "равно"
    if change == 0:
        return f"{metric}: {solver_name} равно {reference_name} (0.00%)."
    return f"{metric}: {solver_name} на {_percent_change(value, reference)} {relation}, чем {reference_name}."


def _print_percent_changes(
    rows: list[
        tuple[
            str,
            float | int | None,
            float | int | None,
            float | int | None,
            float | int | None,
            float | int | None,
            int,
        ]
    ],
) -> None:
    """Печатает процентные изменения включённых solver'ов ниже таблицы."""
    print()
    print("Процентное изменение относительно Baseline и контрольного распределения")
    for name, control, baseline, ortools, ico, timefold, _ in rows:
        print(f"  {_percent_phrase(name, ortools, baseline, 'OR-Tools', 'Baseline')}")
        print(f"  {_percent_phrase(name, ortools, control, 'OR-Tools', 'контрольного распределения')}")
        if ico is not None:
            print(f"  {_percent_phrase(name, ico, baseline, 'ICO-DE', 'Baseline')}")
            print(f"  {_percent_phrase(name, ico, control, 'ICO-DE', 'контрольного распределения')}")
        if timefold is not None:
            print(f"  {_percent_phrase(name, timefold, baseline, 'Timefold', 'Baseline')}")
            print(f"  {_percent_phrase(name, timefold, control, 'Timefold', 'контрольного распределения')}")


def _print_ortools_summary(
    baseline: OptimizationResult,
    ortools: OptimizationResult,
    problem: OptimizationProblem,
) -> None:
    """Печатает краткое сравнение и отдельный пробег OR-Tools для защиты."""
    print("\nOR-Tools относительно Baseline:")
    metrics = (
        ("заявок", baseline.assigned_task_count, ortools.assigned_task_count, "назначил"),
        ("количество инженеров", baseline.used_engineers_count, ortools.used_engineers_count, "сократил"),
        ("пробег", baseline.total_distance, ortools.total_distance, "сократил"),
        ("время движения", baseline.total_travel_time, ortools.total_travel_time, "сократил"),
        ("objective", baseline.total_objective, ortools.total_objective, "уменьшил"),
    )
    for name, reference, value, decrease_verb in metrics:
        if value == reference:
            phrase = (
                "назначил столько же заявок (0.00%)"
                if name == "заявок" else f"не изменил {name} (0.00%)"
            )
        elif reference == 0:
            phrase = f"{name}: Baseline — 0, OR-Tools — {value}; процент не определён"
        elif name == "заявок":
            direction = "больше" if value > reference else "меньше"
            phrase = f"назначил на {_percent_change(value, reference)} {direction} заявок"
        else:
            verb = decrease_verb if value < reference else "увеличил"
            phrase = f"{verb} {name} на {_percent_change(value, reference)}"
        print(f"  - {phrase}.")

    # Короткие ID удобны для презентации; при совпадениях оставляем полные.
    labels = [engineer.id.rsplit("-", 1)[-1] for engineer in problem.engineers]
    if len(set(labels)) != len(labels):
        labels = [engineer.id for engineer in problem.engineers]
    width = max(len("Инженер"), *(len(label) for label in labels))
    print("\nПробег OR-Tools по инженерам:")
    print(f"{'Инженер':<{width}}  {'Пробег, км':>12}")
    print("━" * width + "  " + "━" * 12)
    for index, (engineer, label) in enumerate(zip(problem.engineers, labels)):
        if index:
            print("─" * width + "  " + "─" * 12)
        distance = ortools.distance_by_engineer[engineer.id]
        formatted = "0" if distance == 0 else f"{distance:.3f}"
        print(f"{label:<{width}}  {formatted:>12}")


def _print_distance_by_engineer(
    control_result: OptimizationResult | None,
    baseline_result: OptimizationResult,
    ortools_result: OptimizationResult,
    ico_result: OptimizationResult | None,
    timefold_result: OptimizationResult | None,
    problem: OptimizationProblem,
    *,
    include_ico: bool,
    include_timefold: bool,
) -> None:
    """Печатает пробег каждого инженера для всех доступных вариантов."""
    print()
    print("Пробег по каждому инженеру, км")
    print(
        f"{'Инженер':<30} {'Контрольное':>16} {'Baseline':>16} "
        f"{'OR-Tools':>16}"
        + (f" {'ICO-DE':>16}" if include_ico else "")
        + (f" {'Timefold':>16}" if include_timefold else "")
    )
    print("-" * 100)
    for engineer in problem.engineers:
        control_distance = (
            None
            if control_result is None
            else control_result.distance_by_engineer[engineer.id]
        )
        ico_distance = (
            None
            if ico_result is None
            else ico_result.distance_by_engineer[engineer.id]
        )
        timefold_distance = (
            None
            if timefold_result is None
            else timefold_result.distance_by_engineer[engineer.id]
        )
        line = (
            f"{engineer.id:<30} {_format_value(control_distance, 3):>16} "
            f"{baseline_result.distance_by_engineer[engineer.id]:>16.3f} "
            f"{ortools_result.distance_by_engineer[engineer.id]:>16.3f}"
        )
        if include_ico:
            line += f" {_format_value(ico_distance, 3):>16}"
        if include_timefold:
            line += f" {_format_value(timefold_distance, 3):>16}"
        print(line)


def main(
    default_json_path: Path | None = None,
) -> None:
    """Загружает JSON, проверяет reference-план и печатает сравнение.

    Районные entry point используют одну реализацию и различаются только
    JSON-файлами по умолчанию. CSV является входом генератора JSON и во время
    benchmark больше не читается.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=default_json_path,
        required=default_json_path is None,
        help="JSON-файл района.",
    )
    parser.add_argument("--routing-provider", choices=("coordinate", "osrm"), default="coordinate")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--time-limit-minutes", type=int, default=1)
    parser.add_argument(
        "--timefold-time-limit-seconds",
        type=int,
        default=TimefoldOptimizer.DEFAULT_TIME_LIMIT_SECONDS,
        help="Лимит отдельного запуска Timefold; нужен только его solver.",
    )
    parser.add_argument("--osrm-timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--preserve-assigned",
        action="store_true",
        help="Не разрешать solver переносить заявки со статусом ASSIGNED.",
    )
    parser.add_argument(
        "--ignore-task-statuses",
        action="store_true",
        help="Построить новый план по всем заявкам, игнорируя статусы dataset.",
    )
    parser.add_argument(
        "--consider-equipment",
        action="store_true",
        help="Учитывать расход ограниченного запаса роутеров у инженеров.",
    )
    parser.add_argument(
        "--include-timefold",
        action="store_true",
        help="Дополнительно запустить Timefold, если доступна Java и Python API.",
    )
    parser.add_argument(
        "--include-ico-de",
        action="store_true",
        help="Дополнительно запустить экспериментальный ICO-DE solver.",
    )
    args = parser.parse_args()
    if (
        args.iterations <= 0
        or args.time_limit_minutes <= 0
        or args.timefold_time_limit_seconds <= 0
        or args.osrm_timeout_seconds <= 0
    ):
        parser.error("числовые параметры benchmark должны быть положительными")

    load_started_at = time.perf_counter()
    scenario = load_json_scenario(args.path)
    provider = build_provider(scenario, args.routing_provider, args.osrm_timeout_seconds)
    problem = scenario.to_problem(
        provider,
        preserve_assigned_tasks=args.preserve_assigned and not args.ignore_task_statuses,
        ignore_task_statuses=args.ignore_task_statuses,
        consider_equipment=args.consider_equipment,
    )
    load_seconds = time.perf_counter() - load_started_at

    baseline_measurements, baseline_result = _measure_optimizer(
        GreedyBaselineOptimizer(), problem, args.iterations
    )
    _validate_status_contract("Baseline", problem, baseline_result)
    ortools_measurements, ortools_result = _measure_optimizer(
        ORToolsOptimizer(OptimizerConfig(time_limit_minutes=args.time_limit_minutes)),
        problem,
        args.iterations,
    )
    _validate_status_contract("OR-Tools", problem, ortools_result)
    ico_measurements: list[float] = []
    ico_result: OptimizationResult | None = None
    if args.include_ico_de:
        ico_measurements, ico_result = _measure_optimizer(
            ICOOptimizer(
                OptimizerConfig(time_limit_minutes=args.time_limit_minutes),
                ICORoutingConfig(),
            ),
            problem,
            args.iterations,
        )
        _validate_status_contract("ICO-DE", problem, ico_result)

    timefold_measurements: list[float] = []
    timefold_result: OptimizationResult | None = None
    timefold_error: str | None = None
    if args.include_timefold:
        try:
            timefold_measurements, timefold_result = _measure_timefold(
                TimefoldOptimizer(
                    OptimizerConfig(time_limit_minutes=args.time_limit_minutes),
                    time_limit_seconds=args.timefold_time_limit_seconds,
                ),
                problem,
                args.iterations,
            )
            _validate_status_contract("Timefold", problem, timefold_result)
        except TimefoldUnavailableError as exc:
            # Отсутствие Java/API не должно делать обязательные Baseline и
            # OR-Tools результаты недоступными.
            timefold_error = str(exc)

    control = load_control_dataset_from_scenario(scenario)
    tasks_by_id = {task.id: task for task in problem.tasks}
    # Готовый JSON хранит исполнителя, статус и точный порядок визитов.
    control_planner = ManualAssignmentPlanner(
        # reference_sequence уже хранит точный порядок строк исходного плана.
        control.plan(tasks_by_id, sort_by_window=False).assignments_by_engineer
    )
    control_validation = control_planner.validate(problem)
    control_result: OptimizationResult | None = None
    control_measurements: list[float] = []
    if control.consistent and control_validation.valid:
        control_measurements, control_result = _measure_optimizer(
            control_planner, problem, args.iterations
        )

    print(f"JSON benchmark: {args.path}")
    print(f"Routing provider: {args.routing_provider}")
    print(f"Загружено: {len(problem.engineers)} инженеров, {len(problem.tasks)} заявок")
    status_counts = Counter(task.status.value for task in problem.tasks)
    print(
        "Статусы: "
        + ", ".join(
            f"{status.value}={status_counts.get(status.value, 0)}"
            for status in type(problem.tasks[0].status)
        )
    )
    print(
        f"В новом плане: {len(problem.planning_tasks)} заявок; "
        f"исключено завершённых/отменённых: "
        f"{len(problem.tasks) - len(problem.planning_tasks)}; "
        f"зафиксировано начатых: {len(problem.fixed_task_engineer_by_id)}"
    )
    print(
        "ASSIGNED: "
        + ("назначение сохраняется" if args.preserve_assigned else "перенос разрешён")
    )
    print(
        "Режим статусов: "
        + (
            "статусы игнорируются, строится новый план по всем заявкам"
            if args.ignore_task_statuses
            else "статусы учитываются: CANCELLED/COMPLETED исключены, начатые закреплены"
        )
    )
    print(
        "Учёт роутеров: "
        + ("включён" if args.consider_equipment else "выключен")
    )
    print(f"Импорт и построение матриц: {load_seconds:.6f} с")
    if args.routing_provider == "coordinate":
        print(f"Скорость демонстрационной матрицы: {DEMO_TRAVEL_SPEED_KM_PER_HOUR:g} км/ч")
    print(f"Измерений после прогрева Baseline/OR-Tools: {args.iterations}")
    print(
        "ICO-DE: "
        + ("включён" if args.include_ico_de else "выключен; используйте --include-ico-de")
    )
    print(
        "Timefold: "
        + ("запрошен" if args.include_timefold else "выключен; используйте --include-timefold")
    )
    if args.include_timefold:
        print(f"Лимит Timefold: {args.timefold_time_limit_seconds} с")
        print("Timefold: замер включает холодный запуск JVM")
        if timefold_error is not None:
            print(f"Timefold: пропущен ({timefold_error})")
    print(f"Контрольный план JSON сформирован: {'да' if control.consistent else 'нет'}")
    print(f"Контрольный план соблюдает hard constraints: {'да' if control_validation.valid else 'нет'}")

    if not control_validation.valid:
        reasons = Counter(violation.code for violation in control_validation.violations)
        print(f"Нарушений контрольного плана: {len(control_validation.violations)}")
        print("Причины: " + ", ".join(f"{code}={count}" for code, count in sorted(reasons.items())))
        for violation in control_validation.violations[:10]:
            print(f"  {violation.task_id}: {violation.code} — {violation.message}")

    rows = [
        ("Время расчёта, с", None if control_result is None else statistics.median(control_measurements), statistics.median(baseline_measurements), statistics.median(ortools_measurements), None if ico_result is None else statistics.median(ico_measurements), None if timefold_result is None else statistics.median(timefold_measurements), 6),
        ("Назначено заявок", None if control_result is None else control_result.assigned_task_count, baseline_result.assigned_task_count, ortools_result.assigned_task_count, None if ico_result is None else ico_result.assigned_task_count, None if timefold_result is None else timefold_result.assigned_task_count, 0),
        ("Неназначено заявок", None if control_result is None else control_result.unassigned_task_count, baseline_result.unassigned_task_count, ortools_result.unassigned_task_count, None if ico_result is None else ico_result.unassigned_task_count, None if timefold_result is None else timefold_result.unassigned_task_count, 0),
        ("Задействовано инженеров", None if control_result is None else control_result.used_engineers_count, baseline_result.used_engineers_count, ortools_result.used_engineers_count, None if ico_result is None else ico_result.used_engineers_count, None if timefold_result is None else timefold_result.used_engineers_count, 0),
        ("Пробег, км", None if control_result is None else control_result.total_distance, baseline_result.total_distance, ortools_result.total_distance, None if ico_result is None else ico_result.total_distance, None if timefold_result is None else timefold_result.total_distance, 3),
        ("Время движения, мин", None if control_result is None else control_result.total_travel_time, baseline_result.total_travel_time, ortools_result.total_travel_time, None if ico_result is None else ico_result.total_travel_time, None if timefold_result is None else timefold_result.total_travel_time, 0),
        ("unassigned_penalty", None if control_result is None else control_result.unassigned_penalty, baseline_result.unassigned_penalty, ortools_result.unassigned_penalty, None if ico_result is None else ico_result.unassigned_penalty, None if timefold_result is None else timefold_result.unassigned_penalty, 0),
        ("used_engineers_penalty", None if control_result is None else control_result.used_engineers_penalty, baseline_result.used_engineers_penalty, ortools_result.used_engineers_penalty, None if ico_result is None else ico_result.used_engineers_penalty, None if timefold_result is None else timefold_result.used_engineers_penalty, 0),
        ("distance_penalty", None if control_result is None else control_result.distance_penalty, baseline_result.distance_penalty, ortools_result.distance_penalty, None if ico_result is None else ico_result.distance_penalty, None if timefold_result is None else timefold_result.distance_penalty, 0),
        ("travel_time_penalty", None if control_result is None else control_result.travel_time_penalty, baseline_result.travel_time_penalty, ortools_result.travel_time_penalty, None if ico_result is None else ico_result.travel_time_penalty, None if timefold_result is None else timefold_result.travel_time_penalty, 0),
        ("total_objective", None if control_result is None else control_result.total_objective, baseline_result.total_objective, ortools_result.total_objective, None if ico_result is None else ico_result.total_objective, None if timefold_result is None else timefold_result.total_objective, 0),
    ]
    _print_value_table(rows, include_ico=args.include_ico_de, include_timefold=args.include_timefold)
    _print_percent_changes(rows)
    _print_distance_by_engineer(control_result, baseline_result, ortools_result, ico_result, timefold_result, problem, include_ico=args.include_ico_de, include_timefold=args.include_timefold)
    _print_ortools_summary(baseline_result, ortools_result, problem)


if __name__ == "__main__":
    main()
