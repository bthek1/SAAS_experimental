"""Load-test owners and their definitions (#9). `instances` then seeds from the copies.

Ids are derived from the email and title, exactly as the Django version derives
them, so a run produces the same ids every time and `instances` can create the same
rows from nothing but its copies.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from catalog_fastapi import events
from catalog_fastapi.auth import make_password
from catalog_fastapi.models import BatteryType, BatteryTypeItem, QuestionnaireType, User

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


def seed_owner_types(session: Session, owner: User) -> list[QuestionnaireType]:
    types = [
        QuestionnaireType(
            id=_id(owner.id, "scale", i + 1),
            owner_id=owner.id,
            title=f"Scale {i + 1}",
            questionnaire_json=scored_survey(f"Scale {i + 1}"),
        )
        for i in range(TYPES_PER_OWNER)
    ]
    battery_type = BatteryType(
        id=_id(owner.id, "battery"), owner_id=owner.id, title=BATTERY_TITLE
    )
    session.add_all([*types, battery_type])
    session.flush()
    session.add_all(
        BatteryTypeItem(
            battery_type_id=battery_type.id, questionnaire_type_id=qt.id, order=i
        )
        for i, qt in enumerate(types[:2])
    )
    for instance in [*types, battery_type]:
        events.record_change(session, instance)
    return types


def seed_catalog(session: Session, *, owners: int, password: str) -> SeedResult:
    """Owners and types. Their events reach `instances` after each owner's commit."""
    result = SeedResult()
    # One hash for every owner: they share the password, and hashing is slow.
    encoded = make_password(password)
    for n in range(owners):
        email = owner_email(n)
        if session.scalar(select(exists().where(User.email == email))):
            result.owners_skipped += 1
            continue
        owner = User(id=_id(email), email=email, password=encoded)
        session.add(owner)
        session.flush()
        result.questionnaire_types += len(seed_owner_types(session, owner))
        session.commit()
        result.owners_created += 1
    return result
