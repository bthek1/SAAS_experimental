from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from rest_framework.exceptions import APIException

from . import events, services
from .models import BatteryType, BatteryTypeItem, OutboxEvent, QuestionnaireType


class PublishingAdmin(admin.ModelAdmin):
    """Admin writes reach `instances` the same way API writes do."""

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # After the inlines, so a battery type's event carries its new items.
        events.record_change(form.instance)

    def get_actions(self, request):
        # The bulk action would skip the check with `instances`.
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def delete_model(self, request, obj):  # noqa: ARG002
        services.delete_type(obj)

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except APIException as exc:
            self.message_user(request, str(exc.detail), messages.ERROR)
            opts = self.model._meta
            return redirect(
                reverse(
                    f"admin:{opts.app_label}_{opts.model_name}_change",
                    args=[object_id],
                )
            )


class BatteryTypeItemInline(admin.TabularInline):
    model = BatteryTypeItem
    extra = 0
    autocomplete_fields = ("questionnaire_type",)


@admin.register(QuestionnaireType)
class QuestionnaireTypeAdmin(PublishingAdmin):
    list_display = ("title", "owner", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("title", "owner__email")
    readonly_fields = ("id", "created_at", "updated_at")
    list_select_related = ("owner",)


@admin.register(BatteryType)
class BatteryTypeAdmin(PublishingAdmin):
    list_display = ("title", "owner", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("title", "description", "owner__email")
    readonly_fields = ("id", "created_at", "updated_at")
    list_select_related = ("owner",)
    inlines = [BatteryTypeItemInline]


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "aggregate_id",
        "version",
        "created_at",
        "delivered_at",
        "attempts",
    )
    list_filter = ("event_type", ("delivered_at", admin.EmptyFieldListFilter))
    search_fields = ("aggregate_id",)

    def has_add_permission(self, request):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False
