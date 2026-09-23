"""Модель Job (заявки)."""

from django.db import models


class Job(models.Model):
    """Заявка на выполнение работ (`jobs[]`)."""

    STATUS_SENT = "Отправлена"
    STATUS_IN_PROGRESS = "В работе"
    STATUS_CANCELLED = "Отменена"
    STATUS_DONE = "Выполнена"
    STATUS_CHOICES = [
        (STATUS_SENT, STATUS_SENT),
        (STATUS_IN_PROGRESS, STATUS_IN_PROGRESS),
        (STATUS_CANCELLED, STATUS_CANCELLED),
        (STATUS_DONE, STATUS_DONE),
    ]

    job_id = models.CharField(max_length=64, unique=True)
    territory = models.ForeignKey(
        "Territory", on_delete=models.CASCADE, related_name="jobs",
    )

    request_id = models.BigIntegerField()
    control_request_id = models.BigIntegerField(
        null=True, blank=True, unique=True,
        help_text="Факт. ID заявки в контрольных данных",
    )

    skill_required = models.ForeignKey(
        "Skill", on_delete=models.PROTECT, related_name="jobs",
    )
    request_type_bk = models.CharField(
        max_length=64, help_text="Тип заявки в системе BK",
    )
    request_type_hd = models.CharField(
        max_length=128, help_text="Тип заявки в HelpDesk",
    )

    district = models.ForeignKey(
        "District", on_delete=models.PROTECT, related_name="jobs",
    )
    address = models.CharField(max_length=255)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lon = models.DecimalField(max_digits=9, decimal_places=6)

    window_start = models.TimeField()
    window_end = models.TimeField()
    duration_min = models.PositiveSmallIntegerField()

    time_norm = models.ForeignKey(
        "TimeNorm", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="jobs", help_text="Сопоставлено по time_norm_code",
    )

    priority = models.ForeignKey(
        "Priority", on_delete=models.PROTECT, related_name="jobs",
    )
    required_vehicle = models.ForeignKey(
        "VehicleType", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="required_for_jobs",
    )

    reference_status = models.CharField(
        max_length=32, choices=STATUS_CHOICES,
        help_text="Факт. статус из контрольных данных",
    )
    reference_engineer = models.ForeignKey(
        "Engineer", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reference_jobs",
        help_text="Бригада из reference_crew (сопоставлено по имени)",
    )

    gigabit = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"
        indexes = [
            models.Index(fields=["reference_status"]),
            models.Index(fields=["window_start", "window_end"]),
        ]

    def __str__(self):
        return f"{self.job_id} — {self.address}"