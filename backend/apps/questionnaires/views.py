from django.db.models import Prefetch, RestrictedError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import services
from .models import Battery, BatteryType, Questionnaire, QuestionnaireType
from .serializers import (
    BatterySerializer,
    BatteryTypeSerializer,
    PublicBatterySerializer,
    PublicQuestionnaireSerializer,
    QuestionnaireSerializer,
    QuestionnaireTypeSerializer,
    SubmitSerializer,
)

BY_TOKEN = r"by-token/(?P<share_token>[0-9a-fA-F-]+)"
# Share-link endpoints: no authentication at all, so a stale JWT left in the
# respondent's browser cannot turn into a 401.
PUBLIC = {"permission_classes": [AllowAny], "authentication_classes": []}


class InUse(APIException):
    status_code = 409
    default_detail = (
        "This item is used by existing questionnaires or batteries "
        "and cannot be deleted."
    )
    default_code = "in_use"


class OwnedModelViewSet(viewsets.ModelViewSet):
    """Scopes every query to the requesting user and sets `owner` on create."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    model: type = None  # type: ignore[assignment]

    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except RestrictedError as exc:
            raise InUse() from exc


class QuestionnaireTypeViewSet(OwnedModelViewSet):
    model = QuestionnaireType
    serializer_class = QuestionnaireTypeSerializer


class BatteryTypeViewSet(OwnedModelViewSet):
    model = BatteryType
    serializer_class = BatteryTypeSerializer

    def get_queryset(self):
        return super().get_queryset().prefetch_related("items")

    def perform_create(self, serializer):
        questionnaire_types = serializer.validated_data.pop("questionnaireTypeIds", [])
        battery_type = serializer.save(owner=self.request.user)
        services.set_battery_type_items(battery_type, questionnaire_types)

    def perform_update(self, serializer):
        questionnaire_types = serializer.validated_data.pop(
            "questionnaireTypeIds", None
        )
        battery_type = serializer.save()
        if questionnaire_types is not None:
            services.set_battery_type_items(battery_type, questionnaire_types)
        # UpdateModelMixin clears the prefetched `items` before the response.


class QuestionnaireViewSet(OwnedModelViewSet):
    model = Questionnaire
    serializer_class = QuestionnaireSerializer

    def get_queryset(self):
        return super().get_queryset().select_related("questionnaire_type")

    def _get_by_token(self, share_token: str) -> Questionnaire:
        return get_object_or_404(
            Questionnaire.objects.select_related("questionnaire_type"),
            share_token=share_token,
        )

    @action(detail=False, methods=["get"], url_path=BY_TOKEN, **PUBLIC)
    def by_token(self, request, share_token: str):  # noqa: ARG002
        instance = self._get_by_token(share_token)
        return Response(PublicQuestionnaireSerializer(instance).data)

    @action(detail=False, methods=["patch"], url_path=f"{BY_TOKEN}/submit", **PUBLIC)
    def submit(self, request, share_token: str):
        instance = self._get_by_token(share_token)
        payload = SubmitSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        instance = services.submit_questionnaire(
            instance,
            payload.validated_data["answers"],
            payload.validated_data["metrics"],
        )
        return Response(PublicQuestionnaireSerializer(instance).data)


def with_slots(queryset):
    return queryset.select_related("battery_type").prefetch_related(
        Prefetch(
            "questionnaires",
            queryset=Questionnaire.objects.select_related(
                "questionnaire_type"
            ).order_by("battery_order"),
        )
    )


class BatteryViewSet(OwnedModelViewSet):
    model = Battery
    serializer_class = BatterySerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return with_slots(super().get_queryset())

    @action(detail=False, methods=["get"], url_path=BY_TOKEN, **PUBLIC)
    def by_token(self, request, share_token: str):  # noqa: ARG002
        instance = get_object_or_404(
            with_slots(Battery.objects.all()), share_token=share_token
        )
        return Response(PublicBatterySerializer(instance).data)

    def create(self, request, *args, **kwargs):  # noqa: ARG002
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        battery = services.create_battery(
            serializer.validated_data["battery_type"],
            serializer.validated_data.get("name", ""),
        )
        battery = self.get_queryset().get(pk=battery.pk)
        return Response(
            self.get_serializer(battery).data, status=status.HTTP_201_CREATED
        )
