from collections.abc import Sequence

from django.db import transaction

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
