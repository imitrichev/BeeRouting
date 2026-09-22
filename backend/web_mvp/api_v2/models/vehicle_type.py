"""Модель VehicleType (типы транспорта)."""

from django.db import models


class VehicleType(models.Model):
    """Справочник `dictionaries.vehicle_types`."""

    code = models.SlugField(max_length=32, primary_key=True)
    name = models.CharField(max_length=64)

    class Meta:
        verbose_name = "Тип транспорта"
        verbose_name_plural = "Типы транспорта"

    def __str__(self):
        return self.name