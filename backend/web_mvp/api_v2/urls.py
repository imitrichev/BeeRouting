"""Маршруты CRUD коллеги и прикладных операций планирования API v2."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .views import selectors


router = DefaultRouter()
router.register("engineers", views.EngineerViewSet, basename="engineer")
router.register("jobs", views.JobViewSet, basename="job")
router.register("reschedule-events", views.RescheduleEventViewSet, basename="reschedule-event")

selector_patterns = [
    path("skills/", selectors.skill_list, name="selector-skills"),
    path("vehicle-types/", selectors.vehicle_type_list, name="selector-vehicle-types"),
    path("priorities/", selectors.priority_list, name="selector-priorities"),
    path("time-norms/", selectors.time_norm_list, name="selector-time-norms"),
    path("districts/", selectors.district_list, name="selector-districts"),
    path("territories/", selectors.territory_list, name="selector-territories"),
]


urlpatterns = [
    path("", include(router.urls)),
    path("selectors/", include(selector_patterns)),
    path("territories/", views.territories_view, name="territories"),
    path("dataset/", views.dataset_view, name="dataset"),
    path("dataset/official/", views.official_dataset_view, name="official-dataset"),
    path("dataset/upload/", views.upload_dataset_view, name="upload-dataset"),
    path("tasks/", views.create_task_view, name="create-task"),
    path("geocode/", views.geocode_address_view, name="geocode-address"),
    path("optimize/", views.optimize_view, name="optimize"),
    path("sync-reference-statuses/", views.sync_reference_statuses_view, name="sync-reference-statuses"),
    path("replan/", views.replan_view, name="replan"),
    path("manual-reassignment/preview/", views.manual_reassignment_preview_view, name="manual-reassignment-preview"),
    path("manual-reassignment/confirm/", views.manual_reassignment_confirm_view, name="manual-reassignment-confirm"),
    path("explain/<str:task_id>/", views.explain_task_view, name="explain-task"),
]
