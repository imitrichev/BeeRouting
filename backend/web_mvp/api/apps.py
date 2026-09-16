"""Конфигурация Django-приложения API."""

from django.apps import AppConfig


class ApiConfig(AppConfig):
    """Настройки приложения, которое предоставляет REST API."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "backend.web_mvp.api"
