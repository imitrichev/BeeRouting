"""URL-маршруты Django MVP."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular_extras.views import SpectacularScalarView

urlpatterns = [
    path("api/", include("backend.web_mvp.api.urls")),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/scalar/', SpectacularScalarView.as_view(url_name='schema'), name='docs|scalar'),
]
