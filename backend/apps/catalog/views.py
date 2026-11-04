from rest_framework.response import Response

from apps.utils.cache import bump_owner_generation, cached
from apps.utils.owned import OwnedModelViewSet

from . import services
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
