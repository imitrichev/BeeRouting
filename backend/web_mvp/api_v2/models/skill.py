"""Модель Skill (навыки)."""

from django.db import models


class Skill(models.Model):
    """Справочник `dictionaries.skills`."""

    code = models.SlugField(max_length=64, primary_key=True)
    name = models.CharField(max_length=128)

    class Meta:
        verbose_name = "Навык"
        verbose_name_plural = "Навыки"

    def __str__(self):
        return self.name