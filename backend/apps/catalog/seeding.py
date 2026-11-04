"""The load-test owners and their definitions (#9). See `seed_loadtest`."""

from django.contrib.auth import get_user_model

from . import events
from .models import BatteryType, BatteryTypeItem, QuestionnaireType

TYPES_PER_OWNER = 3


def owner_email(n: int) -> str:
    return f"loadtest-{n}@example.com"


def owner_exists(email: str) -> bool:
    return get_user_model().objects.filter(email=email).exists()


def create_owner(email: str, password: str):
    return get_user_model().objects.create_user(email=email, password=password)


def scored_survey(title: str) -> dict:
    """Two rating questions and the three metric kinds the dashboard reads."""
    return {
        "title": title,
        "pages": [
            {
                "name": "page1",
                "elements": [
                    {"type": "rating", "name": "a", "title": "Item A"},
                    {"type": "rating", "name": "b", "title": "Item B"},
                ],
            }
        ],
        "calculatedValues": [
            {"name": "total", "title": "Total score", "expression": "{a} + {b}"},
            {"name": "severity", "title": "Severity", "expression": "..."},
            {"name": "flag", "title": "Flagged", "expression": "{a} > 4"},
        ],
    }


def seed_owner_types(owner) -> tuple[list[dict], dict]:
    """Create the owner's types, returning a snapshot of each, as events will carry."""
    types = QuestionnaireType.objects.bulk_create(
        QuestionnaireType(
            owner=owner,
            title=f"Scale {i + 1}",
            questionnaire_json=scored_survey(f"Scale {i + 1}"),
        )
        for i in range(TYPES_PER_OWNER)
    )
    battery_type = BatteryType.objects.create(owner=owner, title="Intake battery")
    BatteryTypeItem.objects.bulk_create(
        BatteryTypeItem(battery_type=battery_type, questionnaire_type=qt, order=i)
        for i, qt in enumerate(types[:2])
    )
    for instance in [*types, battery_type]:
        events.record_change(instance)
    return [events.snapshot(qt) for qt in types], events.snapshot(battery_type)
