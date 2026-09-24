"""Модель TimeNorm (нормативы времени)."""

from django.db import models


class TimeNorm(models.Model):
    """Норматив времени из блока `time_norms`.

    `code` — сопоставление с `job.time_norm_code`
    (connection / emergency / equipment_order / local), т.к. в исходном
    JSON нормативы и коды заявок не связаны 1:1 по ключу явно.
    """

    CODE_CONNECTION = "connection"
    CODE_EMERGENCY = "emergency"
    CODE_EQUIPMENT_ORDER = "equipment_order"
    CODE_LOCAL = "local"
    CODE_CHOICES = [
        (CODE_CONNECTION, "Подключение"),
        (CODE_EMERGENCY, "Авария"),
        (CODE_EQUIPMENT_ORDER, "Дозаказ оборудования"),
        (CODE_LOCAL, "Локальная заявка"),
    ]

    code = models.SlugField(
        max_length=32, unique=True, null=True, blank=True,
        choices=CODE_CHOICES,
    )
    name = models.CharField(max_length=128, unique=True)
    road_to_client_min = models.PositiveSmallIntegerField()
    technical_work_min = models.PositiveSmallIntegerField()
    documents_min = models.PositiveSmallIntegerField()
    base_norm_min = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name = "Норматив времени"
        verbose_name_plural = "Нормативы времени"

    def __str__(self):
        return f"{self.name} ({self.base_norm_min} мин)"