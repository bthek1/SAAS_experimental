from rest_framework.routers import DefaultRouter

from .views import (
    BatteryTypeViewSet,
    BatteryViewSet,
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

urlpatterns = router.urls
