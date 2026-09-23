"""Модель District (район)."""

from django.db import models


class District(models.Model):
    """Район внутри территории (поле `district` в заявке)."""

    territory = models.ForeignKey(
        "Territory", on_delete=models.CASCADE, related_name="districts",
    )
    name = models.CharField(max_length=128)

    class Meta:
        verbose_name = "Район"
        verbose_name_plural = "Районы"
        unique_together = ("territory", "name")

    def __str__(self):
        return self.name