"""Модель Engineer (инженеры)."""

from django.db import models


class Engineer(models.Model):
    """Инженер/бригада (`engineers[]`)."""

    engineer_id = models.CharField(max_length=64)
    territory = models.ForeignKey(
        "Territory", on_delete=models.CASCADE, related_name="engineers",
    )
    name = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)

    start_lat = models.DecimalField(max_digits=9, decimal_places=6)
    start_lon = models.DecimalField(max_digits=9, decimal_places=6)

    shift_start = models.TimeField()
    shift_end = models.TimeField()

    skills = models.ManyToManyField(
        "Skill", related_name="engineers",
        help_text="1-3 навыка инженера",
    )
    vehicle_type = models.ForeignKey(
        "VehicleType", on_delete=models.PROTECT, related_name="engineers",
    )

    available_equipment = models.JSONField(default=list)
    available_router_count = models.PositiveIntegerField(default=0)
    start_address = models.CharField(max_length=500, blank=True)

    class Meta:
        unique_together = ('territory', 'engineer_id')
        verbose_name = "Инженер"
        verbose_name_plural = "Инженеры"

    def __str__(self):
        return f"{self.name} ({self.engineer_id})"
