import json
import re
from datetime import UTC

from django.db.models import Prefetch, RestrictedError
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.utils.cache import bump_owner_generation, cached

from . import dashboard, services
from .models import Battery, BatteryType, Questionnaire, QuestionnaireType
from .pdf import generate_response_pdf
from .serializers import (
    BatterySerializer,
    BatteryTypeSerializer,
    DashboardQuerySerializer,
    DashboardScoresQuerySerializer,
    PublicBatterySerializer,
    PublicQuestionnaireSerializer,
    QuestionnaireListQuerySerializer,
    QuestionnaireSerializer,
    QuestionnaireTypeSerializer,
    SubmitSerializer,
)

# New questionnaires, batteries and submissions reach the dashboards within this.
# Invalidating on them would leave little to hit under write-heavy traffic (#11).
DASHBOARD_CACHE_SECONDS = 30
# API writes invalidate these lists at once, so this only bounds admin edits.
TYPE_LIST_CACHE_SECONDS = 5 * 60
PDF_CACHE_SECONDS = 24 * 60 * 60
PDF_CACHE_MAX_BYTES = 2 * 1024 * 1024
# Bump when templates/questionnaires/response_pdf.html changes.
PDF_CACHE_VERSION = 1

BY_TOKEN = r"by-token/(?P<share_token>[0-9a-fA-F-]+)"
# Share-link endpoints: no authentication at all, so a stale JWT left in the
# respondent's browser cannot turn into a 401.
PUBLIC = {"permission_classes": [AllowAny], "authentication_classes": []}


class PDFRenderer(BaseRenderer):
    """Lets clients ask for `Accept: application/pdf`; errors still render as JSON."""

    media_type = "application/pdf"
    format = "pdf"
    charset = None
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):  # noqa: ARG002
        return data if isinstance(data, bytes) else json.dumps(data).encode()


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
        # Newest first, then id: bulk-created rows share a created_at, and a
        # tie would let a row repeat or vanish between pages.
        return self.model.objects.filter(owner=self.request.user).order_by(
            "-created_at", "-id"
        )

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except RestrictedError as exc:
            raise InUse() from exc
        # So a dashboard never links to a deleted row.
        bump_owner_generation(self.request.user.pk)


class CachedListViewSet(OwnedModelViewSet):
    """Caches the paginated list body. Only a 200 is stored: a bad page raises."""

    def list(self, request, *args, **kwargs):
        list_page = super().list
        return Response(
            cached(
                "type-list",
                owner_id=request.user.pk,
                params={
                    "model": self.model.__name__,
                    "page": request.query_params.get("page", "1"),
                    "pageSize": self.paginator.get_page_size(request),
                    # `next` and `previous` are absolute URLs.
                    "scheme": request.scheme,
                    "host": request.get_host(),
                },
                ttl=TYPE_LIST_CACHE_SECONDS,
                compute=lambda: list_page(request, *args, **kwargs).data,
            )
        )


class QuestionnaireTypeViewSet(CachedListViewSet):
    model = QuestionnaireType
    serializer_class = QuestionnaireTypeSerializer

    def perform_create(self, serializer):
        super().perform_create(serializer)
        bump_owner_generation(self.request.user.pk)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        bump_owner_generation(self.request.user.pk)


class BatteryTypeViewSet(CachedListViewSet):
    model = BatteryType
    serializer_class = BatteryTypeSerializer

    def get_queryset(self):
        return super().get_queryset().prefetch_related("items")

    def perform_create(self, serializer):
        questionnaire_types = serializer.validated_data.pop("questionnaireTypeIds", [])
        battery_type = serializer.save(owner=self.request.user)
        services.set_battery_type_items(battery_type, questionnaire_types)
        bump_owner_generation(self.request.user.pk)

    def perform_update(self, serializer):
        questionnaire_types = serializer.validated_data.pop(
            "questionnaireTypeIds", None
        )
        battery_type = serializer.save()
        if questionnaire_types is not None:
            services.set_battery_type_items(battery_type, questionnaire_types)
        # After the items, so a reader cannot cache the old ones as current.
        bump_owner_generation(self.request.user.pk)
        # UpdateModelMixin clears the prefetched `items` before the response.


class QuestionnaireViewSet(OwnedModelViewSet):
    model = Questionnaire
    serializer_class = QuestionnaireSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related("questionnaire_type")
        if self.action != "list":
            return queryset
        query = QuestionnaireListQuerySerializer(
            data=self.request.query_params, context={"request": self.request}
        )
        query.is_valid(raise_exception=True)
        if qtype := query.validated_data.get("questionnaireType"):
            queryset = queryset.filter(questionnaire_type=qtype)
        submitted = query.validated_data["submitted"]
        if submitted is not None:
            queryset = queryset.filter(submitted_at__isnull=not submitted)
        return queryset

    @action(detail=True, methods=["get"], renderer_classes=[JSONRenderer, PDFRenderer])
    def pdf(self, request, pk=None):  # noqa: ARG002
        instance = self.get_object()
        if instance.submitted_at is None:
            raise ValidationError(
                {"detail": "This questionnaire has not been submitted."}
            )
        safe_title = re.sub(r"[^A-Za-z0-9_-]+", "-", instance.questionnaire_type.title)
        filename = (
            f"{safe_title.strip('-')[:60] or 'response'}-{timezone.now().date()}.pdf"
        )
        # A submitted response never changes. The PDF also reads its name and the
        # type's title, so these timestamps identify the content.
        pdf = cached(
            "pdf",
            owner_id=request.user.pk,
            params={
                "id": instance.pk,
                "updatedAt": instance.updated_at,
                "typeUpdatedAt": instance.questionnaire_type.updated_at,
            },
            ttl=PDF_CACHE_SECONDS,
            compute=lambda: generate_response_pdf(instance),
            version=PDF_CACHE_VERSION,
            use_generation=False,
            store_if=lambda content: len(content) <= PDF_CACHE_MAX_BYTES,
        )
        # A binary download, so a plain HttpResponse rather than DRF's Response.
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

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


class DashboardView(APIView):
    def get(self, request):
        query = DashboardQuerySerializer(
            data=request.query_params, context={"request": request}
        )
        query.is_valid(raise_exception=True)
        days = query.validated_data.get("days")
        questionnaire_type = query.validated_data.get("questionnaireType")
        tz = query.validated_data.get("tz", UTC)
        return Response(
            cached(
                "dashboard",
                owner_id=request.user.pk,
                params={
                    "days": days,
                    "questionnaireType": questionnaire_type and questionnaire_type.pk,
                    "tz": str(tz),
                },
                ttl=DASHBOARD_CACHE_SECONDS,
                compute=lambda: dashboard.dashboard_summary(
                    request.user,
                    days=days,
                    questionnaire_type=questionnaire_type,
                    tz=tz,
                ),
            )
        )


class DashboardScoresView(APIView):
    def get(self, request):
        query = DashboardScoresQuerySerializer(
            data=request.query_params, context={"request": request}
        )
        query.is_valid(raise_exception=True)
        days = query.validated_data.get("days")
        questionnaire_type = query.validated_data["questionnaireType"]
        tz = query.validated_data.get("tz", UTC)
        return Response(
            cached(
                "dashboard-scores",
                owner_id=request.user.pk,
                params={
                    "days": days,
                    "questionnaireType": questionnaire_type.pk,
                    "tz": str(tz),
                },
                ttl=DASHBOARD_CACHE_SECONDS,
                version=2,
                compute=lambda: dashboard.dashboard_scores(
                    request.user, questionnaire_type, days=days, tz=tz
                ),
            )
        )
