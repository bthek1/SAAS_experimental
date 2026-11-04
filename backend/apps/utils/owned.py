"""Owner scoping shared by the type and instance APIs."""

from django.db.models import RestrictedError
from rest_framework import serializers, viewsets
from rest_framework.exceptions import APIException

from apps.utils.cache import bump_owner_generation


class InUse(APIException):
    status_code = 409
    default_detail = (
        "This item is used by existing questionnaires or batteries "
        "and cannot be deleted."
    )
    default_code = "in_use"


class OwnedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """Accept only primary keys of objects owned by the requesting user."""

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.context["request"].user)


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
