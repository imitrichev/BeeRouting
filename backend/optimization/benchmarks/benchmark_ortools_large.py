"""Benchmark OR-Tools для крупного сценария.

Сценарий содержит 15 инженеров и 100 заявок. Матрица времени движения
строится детерминированно в памяти, чтобы benchmark не зависел от OSRM.

Запуск из корня проекта:

    .venv/bin/python -m backend.optimization.benchmarks.benchmark_ortools_large

Benchmark не является unit-тестом и не содержит порога производительности.
"""

from __future__ import annotations

import argparse
import statistics
import time

from backend.optimization import (
    Engineer,
    EngineerAvailability,
    InMemoryRoutingProvider,
    OptimizerConfig,
    OptimizationProblem,
    ORToolsOptimizer,
    Skill,
    Task,
    VehicleType,
)


ENGINEER_COUNT = 15
TASK_COUNT = 100


def build_large_problem() -> OptimizationProblem:
    """Создаёт детерминированную задачу с 15 инженерами и 100 заявками."""
    engineers = tuple(
        Engineer(
            id=f"engineer-{engineer_index:03d}",
            name=f"Инженер {engineer_index + 1}",
            qualifications=frozenset({Skill.LOCAL_WORKS}),
            start_location_id=f"base-{engineer_index:03d}",
            vehicle_type=VehicleType.CAR,
        )
        for engineer_index in range(ENGINEER_COUNT)
    )
    availabilities = tuple(
        EngineerAvailability(
            engineer_id=engineer.id,
            available_from="08:00",
            available_until="17:00",
        )
        for engineer in engineers
    )
    tasks = tuple(
        Task(
            id=f"task-{task_index:04d}",
            location_id=f"customer-{task_index:04d}",
            required_skills=frozenset({Skill.LOCAL_WORKS}),
            duration_minutes=10,
            window_start="08:00",
            window_end="17:00",
        )
        for task_index in range(TASK_COUNT)
    )

    location_ids = tuple(
        engineer.start_location_id for engineer in engineers
    ) + tuple(task.location_id for task in tasks)
    travel_time_matrix = {
        from_location: {
            to_location: (
                0
                if from_index == to_index
                else 30 + ((from_index * 17 + to_index * 31) % 600)
            )
            for to_index, to_location in enumerate(location_ids)
        }
        for from_index, from_location in enumerate(location_ids)
    }
    distance_matrix = {
        from_location: {
            to_location: (
                0.0
                if from_index == to_index
                else 1.0 + ((from_index * 13 + to_index * 7) % 500) / 10
            )
            for to_index, to_location in enumerate(location_ids)
        }
        for from_index, from_location in enumerate(location_ids)
    }
    routing_provider = InMemoryRoutingProvider(travel_time_matrix, distance_matrix)
    return OptimizationProblem(
        engineers=engineers,
        availabilities=availabilities,
        tasks=tasks,
        travel_time_matrix=routing_provider.get_travel_time_matrix(location_ids),
        travel_distance_matrix=routing_provider.get_distance_matrix(location_ids),
    )


def run_benchmark(iterations: int) -> list[float]:
    """Измеряет время решения крупной задачи после одного прогрева."""
    problem = build_large_problem()
    optimizer = ORToolsOptimizer(OptimizerConfig(time_limit_minutes=5))

    # Первый запуск исключается, чтобы не смешивать измерение с прогревом
    # внутренних структур OR-Tools и импортированных библиотек.
    optimizer.optimize(problem)

    measurements: list[float] = []
    for _ in range(iterations):
        started_at = time.perf_counter()
        optimizer.optimize(problem)
        measurements.append(time.perf_counter() - started_at)
    return measurements


def main() -> None:
    """Запускает крупный benchmark и печатает его статистику."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Количество измерений после прогрева (по умолчанию: 3)",
    )
    args = parser.parse_args()
    if args.iterations <= 0:
        parser.error("--iterations должен быть положительным")

    measurements = run_benchmark(args.iterations)
    print("OR-Tools large benchmark")
    print(
        f"Сценарий: {ENGINEER_COUNT} инженеров, {TASK_COUNT} заявок, "
        "детерминированная ручная матрица"
    )
    print(f"Измерений: {len(measurements)} (первый запуск исключён как прогрев)")
    print(f"Общее время: {sum(measurements):.6f} с")
    print(f"Среднее:      {statistics.mean(measurements):.6f} с")
    print(f"Медиана:      {statistics.median(measurements):.6f} с")
    print(f"Минимум:      {min(measurements):.6f} с")
    print(f"Максимум:     {max(measurements):.6f} с")
    print(
        "Показатели описывают только локальное время вызова solver’а "
        "для этого сценария."
    )


if __name__ == "__main__":
    main()
