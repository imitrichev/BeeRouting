"""Модель RescheduleEvent (события перепланирования)."""

from django.db import models


class RescheduleEvent(models.Model):
    """Событие из блока `reschedule_events`.

    Три наблюдаемых типа: срочная заявка (urgent_job), отмена заявки
    (cancel_job), недоступность инженера (engineer_unavailable).
    Т.к. полезная нагрузка (payload) отличается по типу, специфичные
    для urgent_job поля дублируются как nullable-поля, а полный
    исходный payload сохраняется в JSONField для трассируемости.
    """

    TYPE_URGENT_JOB = "urgent_job"
    TYPE_CANCEL_JOB = "cancel_job"
    TYPE_ENGINEER_UNAVAILABLE = "engineer_unavailable"
    TYPE_CHOICES = [
        (TYPE_URGENT_JOB, "Новая срочная заявка"),
        (TYPE_CANCEL_JOB, "Отмена заявки"),
        (TYPE_ENGINEER_UNAVAILABLE, "Недоступность инженера"),
    ]

    territory = models.ForeignKey(
        "Territory", on_delete=models.CASCADE, related_name="reschedule_events",
    )
    event_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    time = models.TimeField()

    job = models.ForeignKey(
        "Job", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reschedule_events",
        help_text="Заполняется для cancel_job; для urgent_job — созданная заявка",
    )
    engineer = models.ForeignKey(
        "Engineer", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reschedule_events",
        help_text="Заполняется для engineer_unavailable",
    )

    payload = models.JSONField(
        null=True, blank=True,
        help_text="Сырой payload события для трассируемости",
    )

    class Meta:
        verbose_name = "Событие перепланирования"
        verbose_name_plural = "События перепланирования"
        ordering = ["time"]

    def __str__(self):
        return f"{self.event_type} @ {self.time}"