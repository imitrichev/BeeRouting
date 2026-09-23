"""URL-маршруты для API v2."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import EngineerViewSet, JobViewSet, RescheduleEventViewSet
from .views.core import dataset_view, load_territory_dataset_view, optimize_view
from .views.selectors import *

router = DefaultRouter()
router.register(r"engineers", EngineerViewSet, basename="engineer")
router.register(r"jobs", JobViewSet, basename="job")
router.register(r"reschedule-events", RescheduleEventViewSet, basename="reschedule-event")

selector_urls = [
    path("skill/", skill_list, name="skill"),
    path("vehicle/type/", vehicle_type_list, name="load-dataset"),
    path("priority/", priority_list, name="priority-list"),
    path("time/norm/", time_norm_list, name="time-norm"),
    path("district/", district_list, name="district_list"),
    path("territory/", territory_list, name="territory"),
]

urlpatterns = [
    path("", include(router.urls)),
    path("dataset/", dataset_view, name="dataset"),
    path("dataset/load/", load_territory_dataset_view, name="vehicle-type"),
    path("optimize/", optimize_view, name="optimize"),
    path("selectors/", include(selector_urls))
]