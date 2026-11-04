"""The definitions: what owners build, and instances are made from (#13).

Tables keep their `questionnaires_` names: they moved here without a schema change.
"""

import uuid

from django.conf import settings
from django.db import models


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class QuestionnaireType(TimestampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="questionnaire_types",
    )
    title = models.CharField(max_length=255)
    questionnaire_json = models.JSONField(default=dict, blank=True)

    class Meta(TimestampedModel.Meta):
        db_table = "questionnaires_questionnairetype"
        indexes = [models.Index(fields=["owner", "-created_at"])]

    def __str__(self) -> str:
        return self.title


class BatteryType(TimestampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="battery_types",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    questionnaire_types = models.ManyToManyField(
        QuestionnaireType, through="BatteryTypeItem", related_name="battery_types"
    )

    class Meta(TimestampedModel.Meta):
        db_table = "questionnaires_batterytype"
        indexes = [models.Index(fields=["owner", "-created_at"])]

    def __str__(self) -> str:
        return self.title


class BatteryTypeItem(models.Model):
    battery_type = models.ForeignKey(
        BatteryType, on_delete=models.CASCADE, related_name="items"
    )
    questionnaire_type = models.ForeignKey(
        QuestionnaireType, on_delete=models.RESTRICT, related_name="battery_items"
    )
    order = models.PositiveIntegerField()

    class Meta:
        db_table = "questionnaires_batterytypeitem"
        ordering = ["order"]
        unique_together = [("battery_type", "order")]

    def __str__(self) -> str:
        return f"{self.battery_type} #{self.order}: {self.questionnaire_type}"
