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


# Read-only copies of the definitions, kept current by events from `catalog` (#13).
# Written only by refs.py. Reads never leave this service, which is what lets a
# respondent submit while `catalog` is down. The ids and timestamps are the source's.


class TypeRef(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    version = models.PositiveBigIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class QuestionnaireTypeRef(TypeRef):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="questionnaire_type_refs",
    )
    questionnaire_json = models.JSONField(default=dict, blank=True)

    class Meta(TypeRef.Meta):
        indexes = [models.Index(fields=["owner", "-created_at"])]


class BatteryTypeRef(TypeRef):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="battery_type_refs",
    )
    description = models.TextField(blank=True, default="")

    class Meta(TypeRef.Meta):
        indexes = [models.Index(fields=["owner", "-created_at"])]


class BatteryTypeRefSlot(models.Model):
    """A plain UUID, not a foreign key: a battery type's event can arrive first."""

    battery_type = models.ForeignKey(
        BatteryTypeRef, on_delete=models.CASCADE, related_name="slots"
    )
    questionnaire_type_id = models.UUIDField(db_index=True)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order"]
        unique_together = [("battery_type", "order")]

    def __str__(self) -> str:
        return f"{self.battery_type_id} #{self.order}"


class RetiredRef(models.Model):
    """Stops a late event from bringing back a copy of a deleted type."""

    kind = models.CharField(max_length=32)
    ref_id = models.UUIDField()
    retired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "ref_id"], name="retired_ref_once")
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.ref_id}"


class Battery(TimestampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="batteries"
    )
    battery_type = models.ForeignKey(
        BatteryTypeRef, on_delete=models.RESTRICT, related_name="instances"
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
        QuestionnaireTypeRef, on_delete=models.RESTRICT, related_name="instances"
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
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            # Partial: most dashboard reads only want submitted rows.
            models.Index(
                fields=["owner", "-submitted_at"],
                condition=models.Q(submitted_at__isnull=False),
                name="q_owner_submitted",
            ),
            models.Index(
                fields=["owner", "questionnaire_type", "-submitted_at"],
                condition=models.Q(submitted_at__isnull=False),
                name="q_owner_type_submitted",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.questionnaire_type.title} - {self.name or self.share_token}"
