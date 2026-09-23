"""Модель Priority (приоритеты)."""

from django.db import models


class Priority(models.Model):
    """Справочник `dictionaries.priorities`."""

    code = models.SlugField(max_length=32, primary_key=True)
    name = models.CharField(max_length=64)

    class Meta:
        verbose_name = "Приоритет"
        verbose_name_plural = "Приоритеты"

    def __str__(self):
        return self.name