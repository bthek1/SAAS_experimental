import uuid

from django.db import models

# Owners live in `catalog`, so `owner_id` is a plain UUID here (#13). Deleting a type
# that has instances is blocked (RESTRICT). Deleting a user reaches this service as an
# event, which removes the owner's rows: see refs.py.


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        # `-id` breaks ties: MongoDB stores milliseconds, so rows made together tie.
        # The (owner_id, -created_at, -id) indexes match this order: without `-id`
        # MongoDB sorts every row of the owner to return one page (#30).
        ordering = ["-created_at", "-id"]


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
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.title


class QuestionnaireTypeRef(TypeRef):
    owner_id = models.UUIDField(db_index=True)
    questionnaire_json = models.JSONField(default=dict, blank=True)

    class Meta(TypeRef.Meta):
        indexes = [models.Index(fields=["owner_id", "-created_at", "-id"])]


class BatteryTypeRef(TypeRef):
    owner_id = models.UUIDField(db_index=True)
    description = models.TextField(blank=True, default="")

    class Meta(TypeRef.Meta):
        indexes = [models.Index(fields=["owner_id", "-created_at", "-id"])]


class BatteryTypeRefSlot(models.Model):
    """A plain UUID, not a foreign key: a battery type's event can arrive first."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=32)
    ref_id = models.UUIDField()
    retired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "ref_id"], name="retired_ref_once")
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.ref_id}"


class BlockedOwner(models.Model):
    """Who may no longer reach this service, kept current by events.

    A reactivated owner keeps a row with `blocked` off, so an older deactivation
    arriving late cannot block them again. A deleted owner's stays blocked: their
    token still verifies until it expires, and there is no user here to check.
    """

    owner_id = models.UUIDField(primary_key=True)
    blocked = models.BooleanField(default=True)
    deleted = models.BooleanField(default=False)
    version = models.PositiveBigIntegerField()

    def __str__(self) -> str:
        return str(self.owner_id)


class Battery(TimestampedModel):
    owner_id = models.UUIDField(db_index=True)
    battery_type = models.ForeignKey(
        BatteryTypeRef, on_delete=models.RESTRICT, related_name="instances"
    )
    name = models.CharField(max_length=255, blank=True)
    share_token = models.UUIDField(default=uuid.uuid4, unique=True)

    class Meta(TimestampedModel.Meta):
        verbose_name_plural = "batteries"
        indexes = [models.Index(fields=["owner_id", "-created_at", "-id"])]

    def __str__(self) -> str:
        return f"{self.battery_type.title} - {self.name or self.share_token}"


class Questionnaire(TimestampedModel):
    owner_id = models.UUIDField(db_index=True)
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
            models.Index(fields=["owner_id", "-created_at", "-id"]),
            # Partial: most dashboard reads only want submitted rows. Full on MongoDB,
            # see core/mongodb/base.py.
            models.Index(
                fields=["owner_id", "-submitted_at"],
                condition=models.Q(submitted_at__isnull=False),
                name="q_owner_submitted",
            ),
            models.Index(
                fields=["owner_id", "questionnaire_type", "-submitted_at"],
                condition=models.Q(submitted_at__isnull=False),
                name="q_owner_type_submitted",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.questionnaire_type.title} - {self.name or self.share_token}"
