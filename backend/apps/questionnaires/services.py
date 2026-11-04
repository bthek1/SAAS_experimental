from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from . import refs
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
    with transaction.atomic():
        battery = Battery.objects.create(
            owner=battery_type.owner, battery_type=battery_type, name=name
        )
        Questionnaire.objects.bulk_create(
            Questionnaire(
                owner=battery_type.owner,
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
    """Save a respondent's answers once, snapshotting the type's current definition."""
    with transaction.atomic():
        locked = (
            Questionnaire.objects.select_for_update()
            .select_related("questionnaire_type")
            .get(pk=instance.pk)
        )
        if locked.submitted_at is not None:
            raise AlreadySubmitted()
        locked.answers_json = answers
        locked.metrics_json = metrics
        locked.questionnaire_json_snapshot = (
            locked.questionnaire_type.questionnaire_json
        )
        locked.submitted_at = timezone.now()
        locked.save(
            update_fields=[
                "answers_json",
                "metrics_json",
                "questionnaire_json_snapshot",
                "submitted_at",
                "updated_at",
            ]
        )
    return locked
