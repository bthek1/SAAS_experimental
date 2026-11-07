from typing import Any

from django.utils import timezone
from rest_framework.exceptions import APIException

from . import refs
from .db import atomic
from .models import Battery, BatteryTypeRef, Questionnaire


class AlreadySubmitted(APIException):
    status_code = 409
    default_detail = "Already submitted."
    default_code = "already_submitted"


def create_battery(battery_type: BatteryTypeRef, name: str = "") -> Battery:
    """Create a Battery and one Questionnaire per slot of its type, in order."""
    slots = list(battery_type.slots.order_by("order"))
    # Outside the transaction: this can call `catalog`, and each slot needs a copy.
    refs.ensure_questionnaire_types([slot.questionnaire_type_id for slot in slots])
    with atomic():
        battery = Battery.objects.create(
            owner_id=battery_type.owner_id, battery_type=battery_type, name=name
        )
        Questionnaire.objects.bulk_create(
            Questionnaire(
                owner_id=battery_type.owner_id,
                questionnaire_type_id=slot.questionnaire_type_id,
                battery=battery,
                battery_order=slot.order,
            )
            for slot in slots
        )
    return battery


def submit_questionnaire(
    instance: Questionnaire, answers: dict[str, Any], metrics: dict[str, Any]
) -> Questionnaire:
    """Save a respondent's answers once, snapshotting the type's current definition.

    One conditional update, not a row lock: only a row still unsubmitted matches, so of
    two racing submits exactly one wins and the other is a 409, on Postgres and on
    MongoDB alike (which has no row locks, #29).
    """
    fields = {
        "answers_json": answers,
        "metrics_json": metrics,
        "questionnaire_json_snapshot": instance.questionnaire_type.questionnaire_json,
        "submitted_at": timezone.now(),
    }
    fields["updated_at"] = fields["submitted_at"]
    won = Questionnaire.objects.filter(pk=instance.pk, submitted_at=None).update(
        **fields
    )
    if not won:
        raise AlreadySubmitted()
    for name, value in fields.items():
        setattr(instance, name, value)
    return instance
