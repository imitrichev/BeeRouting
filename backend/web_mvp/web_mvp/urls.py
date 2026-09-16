"""URL-маршруты Django MVP."""

from django.urls import include, path


urlpatterns = [
    path("api/", include("backend.web_mvp.api.urls")),
]
