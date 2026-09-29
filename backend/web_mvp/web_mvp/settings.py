"""Минимальные настройки Django для локального end-to-end MVP."""

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")

BEEROUTING_MODE = os.getenv("BEEROUTING_MODE", "developer").strip().lower()
if BEEROUTING_MODE not in {"developer", "production"}:
    raise ValueError("BEEROUTING_MODE должен быть developer или production")
DEVELOPER_MODE = BEEROUTING_MODE == "developer"

SECRET_KEY = "development-only-beerouting-mvp"
DEBUG = DEVELOPER_MODE
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    'drf_spectacular',
    'drf_spectacular_extras',
    "backend.web_mvp.api_v2",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "backend.web_mvp.web_mvp.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.web_mvp.web_mvp.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "web_mvp.sqlite3",
    }
}

CORS_ALLOW_ALL_ORIGINS = True

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SPECTACULAR_SETTINGS = {
    'TITLE': 'Beeline Case-13',
    'DESCRIPTION': 'API для оптимизации маршрутов операторов ТО',
    'VERSION': '0.0.1',
    'SERVE_INCLUDE_SCHEMA': False,
}

SPECTACULAR_EXTRAS_SETTINGS = {
    'SCALAR_UI_SETTINGS': {
        'theme': 'bluePlanet',
        'layout': 'modern',
        'showSidebar': True,
    }
}

# MVP не требует авторизации. Пустой список отключает SessionAuthentication,
# чтобы POST из локального Vue-приложения не требовал CSRF-токен.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema'
}
