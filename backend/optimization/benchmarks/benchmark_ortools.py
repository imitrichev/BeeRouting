"""Простой benchmark времени решения OR-Tools.

Запуск из корня проекта:

    .venv/bin/python -m backend.optimization.benchmarks.benchmark_ortools

Benchmark не проверяет допустимый порог времени и не является unit-тестом.
Он нужен для наблюдения за текущей производительностью на фиксированном
маленьком сценарии.
"""

from __future__ import annotations

import argparse
import statistics
import time

from backend.optimization import ORToolsOptimizer
from backend.optimization.tests.test_ortools_optimizer import build_problem


def run_benchmark(iterations: int) -> list[float]:
    """Измеряет длительность вызова optimize в секундах."""
    problem = build_problem()
    optimizer = ORToolsOptimizer()

    # Первый запуск прогревает импортированные библиотеки и внутренние
    # структуры OR-Tools и поэтому не включается в измерение.
    optimizer.optimize(problem)

    measurements: list[float] = []
    for _ in range(iterations):
        started_at = time.perf_counter()
        optimizer.optimize(problem)
        measurements.append(time.perf_counter() - started_at)
    return measurements


def main() -> None:
    """Запускает benchmark и печатает измерения на экран."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--iterations",
        type=int,
        default=20,
        help="Количество измеряемых запусков после прогрева (по умолчанию: 20)",
    )
    args = parser.parse_args()
    if args.iterations <= 0:
        parser.error("--iterations должен быть положительным")

    measurements = run_benchmark(args.iterations)
    print("OR-Tools benchmark")
    print("Сценарий: 3 инженера, 5 заявок, ручная матрица времени движения")
    print(f"Измерений: {len(measurements)} (первый запуск исключён как прогрев)")
    print(f"Общее время: {sum(measurements):.6f} с")
    print(f"Среднее:      {statistics.mean(measurements):.6f} с")
    print(f"Медиана:      {statistics.median(measurements):.6f} с")
    print(f"Минимум:      {min(measurements):.6f} с")
    print(f"Максимум:     {max(measurements):.6f} с")
    print(
        "Показатели описывают только локальное время вызова solver’а "
        "для этого маленького сценария."
    )


if __name__ == "__main__":
    main()
