"""Конфигурация математического ядра."""

from dataclasses import dataclass

from .models import Priority, Task, WorkType


@dataclass(frozen=True, slots=True)
class OptimizerConfig:
    """Параметры OR-Tools и веса компонентов целевой функции.

    Время поиска задаётся в минутах. Остальные параметры — веса компонентов
    целевой функции в условных единицах. Большой штраф за неназначение задаёт
    приоритет выполнения заявок, а остальные веса сравнивают допустимые планы.
    """

    time_limit_minutes: int = 5  # Лимит поиска OR-Tools в минутах; после него возвращается лучшее найденное решение.
    used_engineers_penalty: int = 100_000  # Добавка за каждый непустой маршрут; помогает объединять заявки у меньшего числа инженеров.
    distance_penalty_per_km: int = 100  # Сколько условных единиц objective стоит один километр пробега.
    travel_time_penalty_per_minute: int = 1  # Сколько условных единиц objective стоит одна минута движения.
    reassignment_penalty: int = 20_000  # Штраф за перенос ранее назначенной заявки другому инженеру при перепланировании.
    route_order_change_penalty: int = 2_000  # Штраф за изменение предшественника заявки в существующем маршруте.
    unassigned_penalty: int = 1_000_000  # Базовая стоимость пропуска заявки; она выше обычных транспортных затрат.
    normal_unassigned_multiplier: int = 1  # Множитель базового штрафа для заявки с приоритетом NORMAL.
    urgent_unassigned_multiplier: int = 2  # Множитель базового штрафа для URGENT; должен быть больше обычного.
    emergency_unassigned_multiplier: int = 4  # Вес потери аварии — максимальный среди типов работ.
    connection_unassigned_multiplier: int = 2  # Подключение важнее ремонта и дозаказа при дефиците ресурсов.
    local_unassigned_multiplier: int = 1  # Вес потери локальной заявки или ремонта.
    equipment_order_unassigned_multiplier: int = 1  # Вес потери заявки на дозаказ оборудования.
    explanation_time_limit_seconds: int = 2  # Лимит одного counterfactual-расчёта для объяснения.
    explanation_distance_threshold_km: float = 1.0  # Минимальная существенная разница пробега для текста объяснения.
    explanation_travel_time_threshold_minutes: int = 5  # Минимальная существенная разница времени движения.
    explanation_free_reassignments: int = 2  # Сколько переносов допускается в counterfactual-проверке без штрафа.
    explanation_reassignment_penalty: int = 300  # Цена каждого переноса сверх бесплатного порога; 300 соответствует примерно 3 км пробега.

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
        if self.reassignment_penalty < 0:
            raise ValueError("reassignment_penalty не может быть отрицательным")
        if self.route_order_change_penalty < 0:
            raise ValueError("route_order_change_penalty не может быть отрицательным")
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
        if any(
            value <= 0
            for value in (
                self.emergency_unassigned_multiplier,
                self.connection_unassigned_multiplier,
                self.local_unassigned_multiplier,
                self.equipment_order_unassigned_multiplier,
            )
        ):
            raise ValueError(
                "Множители неназначения по WorkType должны быть положительными"
            )
        if self.explanation_time_limit_seconds <= 0:
            raise ValueError("explanation_time_limit_seconds должен быть положительным")
        if self.explanation_distance_threshold_km < 0:
            raise ValueError("explanation_distance_threshold_km не может быть отрицательным")
        if self.explanation_travel_time_threshold_minutes < 0:
            raise ValueError(
                "explanation_travel_time_threshold_minutes не может быть отрицательным"
            )
        if self.explanation_free_reassignments < 0:
            raise ValueError("explanation_free_reassignments не может быть отрицательным")
        if self.explanation_reassignment_penalty < 0:
            raise ValueError("explanation_reassignment_penalty не может быть отрицательным")

    def unassigned_multiplier(self, task: Task) -> int:
        """Возвращает множитель потери заявки по типу выполняемых работ.

        Для старых задач без ``work_type`` применяется прежний приоритет
        NORMAL/URGENT, что сохраняет совместимость внешнего API и тестов.
        """
        by_work_type = {
            WorkType.EMERGENCY: self.emergency_unassigned_multiplier,
            WorkType.CONNECTION: self.connection_unassigned_multiplier,
            WorkType.LOCAL: self.local_unassigned_multiplier,
            WorkType.EQUIPMENT_ORDER: self.equipment_order_unassigned_multiplier,
        }
        if task.work_type is not None:
            return by_work_type[task.work_type]
        return (
            self.urgent_unassigned_multiplier
            if task.priority == Priority.URGENT
            else self.normal_unassigned_multiplier
        )

    def explanation_plan_disruption_penalty(self, reassigned_task_count: int) -> int:
        """Считает штраф stage 2 только за переносы сверх бесплатного порога."""
        charged_count = max(
            0,
            reassigned_task_count - self.explanation_free_reassignments,
        )
        return charged_count * self.explanation_reassignment_penalty
