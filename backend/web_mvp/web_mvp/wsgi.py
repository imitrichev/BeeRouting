"""WSGI-точка входа Django MVP."""

import os

from django.core.wsgi import get_wsgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.web_mvp.web_mvp.settings")
application = get_wsgi_application()
