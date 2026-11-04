from collections.abc import Sequence

from django.db import transaction
from django.db.models import RestrictedError

from apps.utils.owned import InUse
from apps.utils.peers import (
    PeerUnavailable,
    RefInUse,
    ServiceUnavailable,
    instances_client,
)

from . import events
from .models import BatteryType, BatteryTypeItem, QuestionnaireType


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


def delete_type(instance: QuestionnaireType | BatteryType) -> None:
    """Delete a type, once `instances` has confirmed nothing there uses it.

    No database can enforce this across services, so `instances` retires its copy
    first. There the RESTRICT still guards it. Fails closed: if `instances` cannot
    answer, nothing is deleted. If this fails after a successful retire, the type
    still exists here, and the next read-through restores the copy.
    """
    if isinstance(instance, QuestionnaireType) and instance.battery_items.exists():
        raise InUse()
    try:
        instances_client().retire(events.kind_of(instance), instance.pk)
    except RefInUse as exc:
        raise InUse() from exc
    except PeerUnavailable as exc:
        raise ServiceUnavailable() from exc
    try:
        with transaction.atomic():
            events.record_deleted(instance)
            instance.delete()
    except RestrictedError as exc:
        # A battery type picked this type up after the check above.
        raise InUse() from exc
