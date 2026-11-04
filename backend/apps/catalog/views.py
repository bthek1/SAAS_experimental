from django.db import transaction
from rest_framework.response import Response

from apps.utils.cache import bump_owner_generation, cached
from apps.utils.owned import OwnedModelViewSet

from . import events, services
from .models import BatteryType, QuestionnaireType
from .serializers import BatteryTypeSerializer, QuestionnaireTypeSerializer

# API writes invalidate these lists at once, so this only bounds admin edits.
TYPE_LIST_CACHE_SECONDS = 5 * 60


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

    def perform_destroy(self, instance):
        services.delete_type(instance)
        # So a dashboard never links to a deleted row.
        bump_owner_generation(self.request.user.pk)


class QuestionnaireTypeViewSet(CachedListViewSet):
    model = QuestionnaireType
    serializer_class = QuestionnaireTypeSerializer

    def perform_create(self, serializer):
        with transaction.atomic():
            super().perform_create(serializer)
            events.record_change(serializer.instance)
        bump_owner_generation(self.request.user.pk)

    def perform_update(self, serializer):
        with transaction.atomic():
            super().perform_update(serializer)
            events.record_change(serializer.instance)
        bump_owner_generation(self.request.user.pk)


class BatteryTypeViewSet(CachedListViewSet):
    model = BatteryType
    serializer_class = BatteryTypeSerializer

    def get_queryset(self):
        return super().get_queryset().prefetch_related("items")

    def perform_create(self, serializer):
        questionnaire_types = serializer.validated_data.pop("questionnaireTypeIds", [])
        with transaction.atomic():
            battery_type = serializer.save(owner_id=self.request.user.pk)
            services.set_battery_type_items(battery_type, questionnaire_types)
            events.record_change(battery_type)
        bump_owner_generation(self.request.user.pk)

    def perform_update(self, serializer):
        questionnaire_types = serializer.validated_data.pop(
            "questionnaireTypeIds", None
        )
        with transaction.atomic():
            battery_type = serializer.save()
            if questionnaire_types is not None:
                services.set_battery_type_items(battery_type, questionnaire_types)
            events.record_change(battery_type)
        # After the items, so a reader cannot cache the old ones as current.
        bump_owner_generation(self.request.user.pk)
        # UpdateModelMixin clears the prefetched `items` before the response.
