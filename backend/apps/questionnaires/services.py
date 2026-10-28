from collections.abc import Sequence
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from .models import (
    Battery,
    BatteryType,
    BatteryTypeItem,
    Questionnaire,
    QuestionnaireType,
)


class AlreadySubmitted(APIException):
    status_code = 409
    default_detail = "Already submitted."
    default_code = "already_submitted"


def set_battery_type_items(
    battery_type: BatteryType, questionnaire_types: Sequence[QuestionnaireType]
) -> None:
    """Replace the battery type's ordered list of questionnaire types."""
    with transaction.atomic():
        battery_type.items.all().delete()
        BatteryTypeItem.objects.bulk_create(
            BatteryTypeItem(battery_type=battery_type, questionnaire_type=qt, order=i)
            for i, qt in enumerate(questionnaire_types)
        )


@transaction.atomic
def create_battery(battery_type: BatteryType, name: str = "") -> Battery:
    """Create a Battery and one Questionnaire per item of its type, in order."""
    battery = Battery.objects.create(
        owner=battery_type.owner, battery_type=battery_type, name=name
    )
    Questionnaire.objects.bulk_create(
        Questionnaire(
            owner=battery_type.owner,
            questionnaire_type_id=item.questionnaire_type_id,
            battery=battery,
            battery_order=item.order,
        )
        for item in battery_type.items.order_by("order")
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
