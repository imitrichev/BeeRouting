"""Модель Territory (территория обслуживания)."""

from django.db import models


class Territory(models.Model):
    """Территория обслуживания (`territory_code` / `territory_name`)."""

    code = models.SlugField(
        max_length=64, unique=True,
        help_text="territory_code, напр. yugo_tsentr",
    )
    name = models.CharField(max_length=128, help_text="territory_name")

    office_lat = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="office_start_point.lat",
    )
    office_lon = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="office_start_point.lon",
    )

    class Meta:
        verbose_name = "Территория"
        verbose_name_plural = "Территории"

    def __str__(self):
        return self.name