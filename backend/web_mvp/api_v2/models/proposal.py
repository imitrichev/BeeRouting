"""Предложение ручного назначения, привязанное к версии плана района."""
from django.db import models


class ReassignmentProposal(models.Model):
    """Preview переживает перезапуск процесса, но не изменение исходного плана."""
    token = models.CharField(max_length=64, primary_key=True)
    territory = models.ForeignKey('Territory', on_delete=models.CASCADE)
    revision = models.PositiveIntegerField()
    payload = models.JSONField()
