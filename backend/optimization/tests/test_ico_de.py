"""Проверки независимого непрерывного ядра ICO/DE."""

import numpy as np

from backend.optimization.ico_de import (
    CountriesAlgorithm,
    ICOConfig,
    from_gray_code,
    to_gray_code,
)


def test_gray_code_round_trip() -> None:
    """Кодирование Грея не меняет исходное целое после декодирования."""
    for value in (0, 1, 2, 17, 255, 65_535):
        assert from_gray_code(to_gray_code(value)) == value


def test_ico_de_converges_and_is_reproducible() -> None:
    """Два запуска с одним seed одинаково минимизируют функцию сферы."""
    config = ICOConfig(
        x_min=[-5.0, -5.0],
        x_max=[5.0, 5.0],
        countries_count=4,
        country_population=10,
        maximum_iterations=80,
        random_seed=42,
    )
    first = CountriesAlgorithm(lambda x: float(x @ x), config).start(max_calls=3_000)
    second = CountriesAlgorithm(lambda x: float(x @ x), config).start(max_calls=3_000)

    assert first.objective < 0.1
    assert first.objective == second.objective
    np.testing.assert_array_equal(first.x, second.x)


def test_initial_solution_is_not_lost() -> None:
    """Переданная точка входит в популяцию до начала оптимизации."""
    config = ICOConfig(
        x_min=[-10.0],
        x_max=[10.0],
        countries_count=2,
        country_population=4,
        maximum_iterations=1,
        initial_x=[0.0],
        random_seed=7,
    )
    result = CountriesAlgorithm(lambda x: float(x[0] ** 2), config).start(max_calls=1)
    assert result.objective == 0.0


def test_ico_de_improves_rosenbrock_in_30_dimensions() -> None:
    """ICO/DE улучшает известную стартовую точку функции Розенброка в 30D.

    Глобальный минимум функции расположен в точке ``x = (1, ..., 1)`` и равен
    нулю. Для стартовой точки ``x = (0, ..., 0)`` значение равно 29. Тест не
    требует достижения глобального минимума за небольшой тестовый бюджет, но
    проверяет, что алгоритм действительно находит решение лучше стартового.
    """

    def rosenbrock_30d(x: np.ndarray) -> float:
        """Считает сумму связанных парабол Розенброка по 29 соседним парам."""
        # Каждый член штрафует отклонение x[i+1] от x[i]² и x[i] от единицы.
        return float(
            np.sum(
                100.0 * (x[1:] - x[:-1] ** 2) ** 2
                + (1.0 - x[:-1]) ** 2
            )
        )

    config = ICOConfig(
        x_min=[-5.0] * 30,
        x_max=[10.0] * 30,
        countries_count=6,
        country_population=20,
        maximum_iterations=120,
        gray_country_fraction=0.0,
        initial_x=[0.0] * 30,
        random_seed=42,
    )

    result = CountriesAlgorithm(rosenbrock_30d, config).start(max_calls=10_000)

    assert result.objective < 29.0
    assert result.function_evaluations <= 10_000
