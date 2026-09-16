"""URL API для загрузки dataset и запуска оптимизации."""

from django.urls import path

from . import views


urlpatterns = [
    path("dataset/", views.dataset_view, name="dataset"),
    path("dataset/official/", views.official_dataset_view, name="official-dataset"),
    path("dataset/upload/", views.upload_dataset_view, name="upload-dataset"),
    path("optimize/", views.optimize_view, name="optimize"),
]
