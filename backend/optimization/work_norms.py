"""Официальные нормативы работ после прибытия инженера на объект."""

from dataclasses import dataclass
from enum import Enum

from .models import Skill


class WorkType(str, Enum):
    """Тип работы, который выбирает диспетчер при создании заявки."""

    CONNECTION = "CONNECTION"
    EMERGENCY = "EMERGENCY"
    EQUIPMENT_ORDER = "EQUIPMENT_ORDER"
    LOCAL = "LOCAL"


@dataclass(frozen=True, slots=True)
class WorkNorm:
    """Длительность работы и необходимая квалификация инженера."""

    title: str
    duration_minutes: int
    required_skill: Skill


WORK_NORMS: dict[WorkType, WorkNorm] = {
    WorkType.CONNECTION: WorkNorm(
        "Подключение клиентов", 70, Skill.CONNECTION_AND_UPSELL
    ),
    WorkType.EMERGENCY: WorkNorm("Авария на ТКД", 80, Skill.EMERGENCY_WORKS),
    WorkType.EQUIPMENT_ORDER: WorkNorm(
        "Дозаказ оборудования", 20, Skill.CONNECTION_AND_UPSELL
    ),
    WorkType.LOCAL: WorkNorm(
        "Локальная заявка / ремонт", 30, Skill.LOCAL_WORKS
    ),
}
