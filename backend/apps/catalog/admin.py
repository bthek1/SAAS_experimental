from django.contrib import admin

from .models import BatteryType, BatteryTypeItem, QuestionnaireType


class BatteryTypeItemInline(admin.TabularInline):
    model = BatteryTypeItem
    extra = 0
    autocomplete_fields = ("questionnaire_type",)


@admin.register(QuestionnaireType)
class QuestionnaireTypeAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("title", "owner__email")
    readonly_fields = ("id", "created_at", "updated_at")
    list_select_related = ("owner",)


@admin.register(BatteryType)
class BatteryTypeAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("title", "description", "owner__email")
    readonly_fields = ("id", "created_at", "updated_at")
    list_select_related = ("owner",)
    inlines = [BatteryTypeItemInline]
