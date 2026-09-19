"""Сравнение контрольного распределения, Baseline и OR-Tools на dataset."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import statistics
import time

from backend.optimization import (
    CoordinateRoutingProvider,
    GreedyBaselineOptimizer,
    JsonScenario,
    ManualAssignmentPlanner,
    OptimizationProblem,
    OptimizationResult,
    OptimizerConfig,
    ORToolsOptimizer,
    OSRMRoutingProvider,
    create_osrm_provider_from_environment,
    RouteOptimizer,
    load_control_dataset,
    load_json_scenario,
    TimefoldOptimizer,
    TimefoldUnavailableError,
)


DEMO_TRAVEL_SPEED_KM_PER_HOUR = 30.0
DEFAULT_JSON_PATH = Path("yugo_center.json")
DEFAULT_CONTROL_CSV_PATH = Path("yugo_center.csv")


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
            int,
        ]
    ],
) -> None:
    """Печатает значения всех вариантов без абсолютных изменений."""
    print()
    print(
        f"{'Метрика':<30} {'Контрольное':>16} {'Baseline':>16} "
        f"{'OR-Tools':>16} {'Timefold':>16}"
    )
    print("-" * 100)
    for name, control, baseline, ortools, timefold, decimals in rows:
        print(
            f"{name:<30} {_format_value(control, decimals):>16} "
            f"{_format_value(baseline, decimals):>16} "
            f"{_format_value(ortools, decimals):>16} "
            f"{_format_value(timefold, decimals):>16}"
        )


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
            int,
        ]
    ],
) -> None:
    """Печатает процентные изменения OR-Tools и Timefold ниже таблицы."""
    print()
    print("Процентное изменение относительно Baseline и контрольного распределения")
    for name, control, baseline, ortools, timefold, _ in rows:
        print(f"  {_percent_phrase(name, ortools, baseline, 'OR-Tools', 'Baseline')}")
        print(f"  {_percent_phrase(name, ortools, control, 'OR-Tools', 'контрольного распределения')}")
        print(f"  {_percent_phrase(name, timefold, baseline, 'Timefold', 'Baseline')}")
        print(f"  {_percent_phrase(name, timefold, control, 'Timefold', 'контрольного распределения')}")


def _print_distance_by_engineer(
    control_result: OptimizationResult | None,
    baseline_result: OptimizationResult,
    ortools_result: OptimizationResult,
    timefold_result: OptimizationResult | None,
    problem: OptimizationProblem,
) -> None:
    """Печатает пробег каждого инженера для всех доступных вариантов."""
    print()
    print("Пробег по каждому инженеру, км")
    print(
        f"{'Инженер':<30} {'Контрольное':>16} {'Baseline':>16} "
        f"{'OR-Tools':>16} {'Timefold':>16}"
    )
    print("-" * 100)
    for engineer in problem.engineers:
        control_distance = (
            None
            if control_result is None
            else control_result.distance_by_engineer[engineer.id]
        )
        timefold_distance = (
            None
            if timefold_result is None
            else timefold_result.distance_by_engineer[engineer.id]
        )
        print(
            f"{engineer.id:<30} {_format_value(control_distance, 3):>16} "
            f"{baseline_result.distance_by_engineer[engineer.id]:>16.3f} "
            f"{ortools_result.distance_by_engineer[engineer.id]:>16.3f} "
            f"{_format_value(timefold_distance, 3):>16}"
        )


def main() -> None:
    """Загружает JSON/CSV, проверяет контроль и печатает сравнение."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--control-csv", type=Path, default=DEFAULT_CONTROL_CSV_PATH)
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
    problem = scenario.to_problem(provider)
    load_seconds = time.perf_counter() - load_started_at

    baseline_measurements, baseline_result = _measure_optimizer(
        GreedyBaselineOptimizer(), problem, args.iterations
    )
    ortools_measurements, ortools_result = _measure_optimizer(
        ORToolsOptimizer(OptimizerConfig(time_limit_minutes=args.time_limit_minutes)),
        problem,
        args.iterations,
    )
    timefold_measurements: list[float] = []
    timefold_result: OptimizationResult | None = None
    timefold_error: str | None = None
    try:
        timefold_measurements, timefold_result = _measure_timefold(
            TimefoldOptimizer(
                OptimizerConfig(time_limit_minutes=args.time_limit_minutes),
                time_limit_seconds=args.timefold_time_limit_seconds,
            ),
            problem,
            args.iterations,
        )
    except TimefoldUnavailableError as exc:
        timefold_error = str(exc)

    control = load_control_dataset(args.control_csv, scenario)
    tasks_by_id = {task.id: task for task in problem.tasks}
    # В CSV задан исполнитель, но не задан порядок визитов. Сначала заявки
    # сортируются по окнам, после чего их расписание проверяется как ручное.
    control_planner = ManualAssignmentPlanner(
        control.plan(tasks_by_id).assignments_by_engineer
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
    print(f"Импорт и построение матриц: {load_seconds:.6f} с")
    if args.routing_provider == "coordinate":
        print(f"Скорость демонстрационной матрицы: {DEMO_TRAVEL_SPEED_KM_PER_HOUR:g} км/ч")
    print(f"Измерений после прогрева Baseline/OR-Tools: {args.iterations}")
    print(f"Лимит Timefold: {args.timefold_time_limit_seconds} с")
    print("Timefold: замер включает холодный запуск JVM")
    if timefold_error is not None:
        print(f"Timefold: недоступен ({timefold_error})")
    print(f"CSV/JSON контроль согласован: {'да' if control.consistent else 'нет'}")
    print(f"Контрольный план соблюдает hard constraints: {'да' if control_validation.valid else 'нет'}")

    if not control_validation.valid:
        reasons = Counter(violation.code for violation in control_validation.violations)
        print(f"Нарушений контрольного плана: {len(control_validation.violations)}")
        print("Причины: " + ", ".join(f"{code}={count}" for code, count in sorted(reasons.items())))
        for violation in control_validation.violations[:10]:
            print(f"  {violation.task_id}: {violation.code} — {violation.message}")

    rows = [
        ("Время расчёта, с", None if control_result is None else statistics.median(control_measurements), statistics.median(baseline_measurements), statistics.median(ortools_measurements), None if timefold_result is None else statistics.median(timefold_measurements), 6),
        ("Назначено заявок", None if control_result is None else control_result.assigned_task_count, baseline_result.assigned_task_count, ortools_result.assigned_task_count, None if timefold_result is None else timefold_result.assigned_task_count, 0),
        ("Неназначено заявок", None if control_result is None else control_result.unassigned_task_count, baseline_result.unassigned_task_count, ortools_result.unassigned_task_count, None if timefold_result is None else timefold_result.unassigned_task_count, 0),
        ("Задействовано инженеров", None if control_result is None else control_result.used_engineers_count, baseline_result.used_engineers_count, ortools_result.used_engineers_count, None if timefold_result is None else timefold_result.used_engineers_count, 0),
        ("Пробег, км", None if control_result is None else control_result.total_distance, baseline_result.total_distance, ortools_result.total_distance, None if timefold_result is None else timefold_result.total_distance, 3),
        ("Время движения, мин", None if control_result is None else control_result.total_travel_time, baseline_result.total_travel_time, ortools_result.total_travel_time, None if timefold_result is None else timefold_result.total_travel_time, 0),
        ("unassigned_penalty", None if control_result is None else control_result.unassigned_penalty, baseline_result.unassigned_penalty, ortools_result.unassigned_penalty, None if timefold_result is None else timefold_result.unassigned_penalty, 0),
        ("used_engineers_penalty", None if control_result is None else control_result.used_engineers_penalty, baseline_result.used_engineers_penalty, ortools_result.used_engineers_penalty, None if timefold_result is None else timefold_result.used_engineers_penalty, 0),
        ("distance_penalty", None if control_result is None else control_result.distance_penalty, baseline_result.distance_penalty, ortools_result.distance_penalty, None if timefold_result is None else timefold_result.distance_penalty, 0),
        ("travel_time_penalty", None if control_result is None else control_result.travel_time_penalty, baseline_result.travel_time_penalty, ortools_result.travel_time_penalty, None if timefold_result is None else timefold_result.travel_time_penalty, 0),
        ("total_objective", None if control_result is None else control_result.total_objective, baseline_result.total_objective, ortools_result.total_objective, None if timefold_result is None else timefold_result.total_objective, 0),
    ]
    _print_value_table(rows)
    _print_percent_changes(rows)
    _print_distance_by_engineer(control_result, baseline_result, ortools_result, timefold_result, problem)


if __name__ == "__main__":
    main()
