import uuid

from django.conf import settings
from django.db import models

# Instances (Battery, Questionnaire) carry their own `owner` as well as their type's.
# Deleting a type that has instances is blocked (RESTRICT), but deleting a user still
# works: every row is reached by a CASCADE through `owner`, which RESTRICT permits.


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
        ordering = ["order"]
        unique_together = [("battery_type", "order")]

    def __str__(self) -> str:
        return f"{self.battery_type} #{self.order}: {self.questionnaire_type}"


class Battery(TimestampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="batteries"
    )
    battery_type = models.ForeignKey(
        BatteryType, on_delete=models.RESTRICT, related_name="instances"
    )
    name = models.CharField(max_length=255, blank=True)
    share_token = models.UUIDField(default=uuid.uuid4, unique=True)

    class Meta(TimestampedModel.Meta):
        verbose_name_plural = "batteries"
        indexes = [models.Index(fields=["owner", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.battery_type.title} - {self.name or self.share_token}"


class Questionnaire(TimestampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="questionnaires",
    )
    questionnaire_type = models.ForeignKey(
        QuestionnaireType, on_delete=models.RESTRICT, related_name="instances"
    )
    battery = models.ForeignKey(
        Battery,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questionnaires",
    )
    battery_order = models.PositiveIntegerField(null=True, blank=True)
    name = models.CharField(max_length=255, blank=True)
    share_token = models.UUIDField(default=uuid.uuid4, unique=True)
    answers_json = models.JSONField(default=dict, blank=True)
    questionnaire_json_snapshot = models.JSONField(default=dict, blank=True)
    metrics_json = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimestampedModel.Meta):
        indexes = [models.Index(fields=["owner", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.questionnaire_type.title} - {self.name or self.share_token}"
