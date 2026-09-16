"""Минимальные настройки Django для локального end-to-end MVP."""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
SECRET_KEY = "development-only-beerouting-mvp"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "rest_framework",
    "backend.web_mvp.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "backend.web_mvp.web_mvp.urls"
TEMPLATES = []
WSGI_APPLICATION = "backend.web_mvp.web_mvp.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "web_mvp.sqlite3",
    }
}

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# MVP не требует авторизации. Пустой список отключает SessionAuthentication,
# чтобы POST из локального Vue-приложения не требовал CSRF-токен.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
}
