from rest_framework.routers import DefaultRouter

from .views import BatteryTypeViewSet, QuestionnaireTypeViewSet

router = DefaultRouter()
router.include_root_view = False
router.register(
    "questionnaire-types", QuestionnaireTypeViewSet, basename="questionnaire-type"
)
router.register("battery-types", BatteryTypeViewSet, basename="battery-type")

urlpatterns = router.urls
