"""Load-test owners and their definitions (#9). `instances` then seeds from the copies.

Ids are derived from the email and title, so a run produces the same ids every time,
and `instances` can create the same rows from nothing but its copies.
"""

import uuid
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction

from . import events
from .models import BatteryType, BatteryTypeItem, QuestionnaireType

TYPES_PER_OWNER = 3
BATTERY_TITLE = "Intake battery"
NAMESPACE = uuid.UUID("7d1c3a52-7c8e-4f5e-9f6d-2a7b5f0c1e11")


def owner_email(n: int) -> str:
    return f"loadtest-{n}@example.com"


def _id(*parts) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, "/".join(str(part) for part in parts))


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


@dataclass
class SeedResult:
    owners_created: int = 0
    owners_skipped: int = 0
    questionnaire_types: int = 0


def seed_owner_types(owner) -> list[QuestionnaireType]:
    types = QuestionnaireType.objects.bulk_create(
        QuestionnaireType(
            id=_id(owner.pk, "scale", i + 1),
            owner=owner,
            title=f"Scale {i + 1}",
            questionnaire_json=scored_survey(f"Scale {i + 1}"),
        )
        for i in range(TYPES_PER_OWNER)
    )
    battery_type = BatteryType.objects.create(
        id=_id(owner.pk, "battery"), owner=owner, title=BATTERY_TITLE
    )
    BatteryTypeItem.objects.bulk_create(
        BatteryTypeItem(battery_type=battery_type, questionnaire_type=qt, order=i)
        for i, qt in enumerate(types[:2])
    )
    for instance in [*types, battery_type]:
        events.record_change(instance)
    return types


def seed_catalog(*, owners: int, password: str) -> SeedResult:
    """Owners and types. Their events reach `instances` after each owner's commit."""
    user_model = get_user_model()
    result = SeedResult()
    for n in range(owners):
        email = owner_email(n)
        if user_model.objects.filter(email=email).exists():
            result.owners_skipped += 1
            continue
        with transaction.atomic():
            owner = user_model.objects.create_user(
                id=_id(email), email=email, password=password
            )
            result.questionnaire_types += len(seed_owner_types(owner))
        result.owners_created += 1
    return result
