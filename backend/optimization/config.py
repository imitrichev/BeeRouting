"""Конфигурация математического ядра."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OptimizerConfig:
    """Параметры OR-Tools и веса компонентов целевой функции.

    Время поиска задаётся в минутах. Остальные параметры — веса компонентов
    целевой функции в условных единицах.
    """

    time_limit_minutes: int = 5
    used_engineers_penalty: int = 100_000
    distance_penalty_per_km: int = 100
    travel_time_penalty_per_minute: int = 1
    unassigned_penalty: int = 1_000_000
    normal_unassigned_multiplier: int = 1
    urgent_unassigned_multiplier: int = 2

    def __post_init__(self) -> None:
        """Проверяет числовые параметры конфигурации."""
        if self.time_limit_minutes <= 0:
            raise ValueError("time_limit_minutes должен быть положительным")
        if self.used_engineers_penalty < 0:
            raise ValueError("used_engineers_penalty не может быть отрицательным")
        if self.distance_penalty_per_km < 0:
            raise ValueError("distance_penalty_per_km не может быть отрицательным")
        if self.travel_time_penalty_per_minute < 0:
            raise ValueError(
                "travel_time_penalty_per_minute не может быть отрицательным"
            )
        if self.unassigned_penalty <= 0:
            raise ValueError("unassigned_penalty должен быть положительным")
        if self.normal_unassigned_multiplier <= 0:
            raise ValueError("normal_unassigned_multiplier должен быть положительным")
        if self.urgent_unassigned_multiplier <= 0:
            raise ValueError("urgent_unassigned_multiplier должен быть положительным")
        if self.urgent_unassigned_multiplier <= self.normal_unassigned_multiplier:
            raise ValueError(
                "urgent_unassigned_multiplier должен быть больше normal_unassigned_multiplier"
            )
