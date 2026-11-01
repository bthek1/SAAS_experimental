from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BatteryTypeViewSet,
    BatteryViewSet,
    DashboardScoresView,
    DashboardView,
    QuestionnaireTypeViewSet,
    QuestionnaireViewSet,
)

router = DefaultRouter()
router.include_root_view = False
router.register(
    "questionnaire-types", QuestionnaireTypeViewSet, basename="questionnaire-type"
)
router.register("questionnaires", QuestionnaireViewSet, basename="questionnaire")
router.register("battery-types", BatteryTypeViewSet, basename="battery-type")
router.register("batteries", BatteryViewSet, basename="battery")

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("dashboard/scores/", DashboardScoresView.as_view(), name="dashboard-scores"),
    *router.urls,
]
