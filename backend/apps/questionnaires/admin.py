from django.contrib import admin

from .models import Battery, BatteryTypeRef, Questionnaire, QuestionnaireTypeRef


class ReadOnlyAdmin(admin.ModelAdmin):
    """Copies change only through events from `catalog`."""

    def has_add_permission(self, request):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False

    def has_delete_permission(self, request, obj=None):  # noqa: ARG002
        return False


@admin.register(QuestionnaireTypeRef, BatteryTypeRef)
class TypeRefAdmin(ReadOnlyAdmin):
    list_display = ("title", "owner", "version", "updated_at")
    search_fields = ("title",)


@admin.register(Battery)
class BatteryAdmin(admin.ModelAdmin):
    list_display = ("id", "battery_type", "name", "owner", "share_token", "created_at")
    list_filter = ("created_at",)
    search_fields = ("battery_type__title", "name", "owner__email")
    readonly_fields = ("id", "share_token", "created_at", "updated_at")
    list_select_related = ("battery_type", "owner")


@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "questionnaire_type",
        "name",
        "owner",
        "submitted_at",
        "created_at",
    )
    list_filter = ("submitted_at",)
    search_fields = ("questionnaire_type__title", "name", "owner__email")
    readonly_fields = ("id", "share_token", "submitted_at", "created_at", "updated_at")
    list_select_related = ("questionnaire_type", "owner")
