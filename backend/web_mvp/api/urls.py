"""URL API для загрузки dataset и запуска оптимизации."""

from django.urls import path

from . import views


urlpatterns = [
    path("dataset/", views.dataset_view, name="dataset"),
    path("dataset/official/", views.official_dataset_view, name="official-dataset"),
    path("dataset/upload/", views.upload_dataset_view, name="upload-dataset"),
    path("tasks/", views.create_task_view, name="create-task"),
    path("geocode/", views.geocode_address_view, name="geocode-address"),
    path("optimize/", views.optimize_view, name="optimize"),
    path("replan/", views.replan_view, name="replan"),
    path("manual-reassignment/preview/", views.manual_reassignment_preview_view, name="manual-reassignment-preview"),
    path("manual-reassignment/confirm/", views.manual_reassignment_confirm_view, name="manual-reassignment-confirm"),
    path("explain/<str:task_id>/", views.explain_task_view, name="explain-task"),
]
