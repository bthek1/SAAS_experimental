"""Writes, and the rules Django kept in `on_delete` and signals (#35).

Django emulates CASCADE and RESTRICT in Python, so the database has neither. Here
the same rules are explicit: a battery type's items go with it, and a questionnaire
type in a battery type cannot go. Every type write records an outbox event in the
same transaction, and bumps the owner's cache generation after the commit.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import events
from .auth import make_password
from .cache import bump_owner_generation
from .errors import InUse, ServiceUnavailable, ValidationError
from .metrics import RETIRE_FAILURES
from .models import (
    DJANGO_USER_LINKS,
    BatteryType,
    BatteryTypeItem,
    QuestionnaireType,
    User,
    now,
)
from .peers import PeerUnavailable, RefInUse, instances_client

DUPLICATE_EMAIL = "custom user with this email already exists."


# ── Users ──────────────────────────────────────────────────────────────────────


def email_taken(session: Session, email: str, *, other_than=None) -> bool:
    query = select(exists().where(User.email == email))
    if other_than is not None:
        query = select(exists().where(User.email == email, User.id != other_than))
    return bool(session.scalar(query))


def create_user(session: Session, email: str, password: str, **fields) -> User:
    if email_taken(session, email):
        raise ValidationError({"email": [DUPLICATE_EMAIL]})
    user = User(email=email, password=make_password(password), **fields)
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        # Registered by another request since the check.
        session.rollback()
        raise ValidationError({"email": [DUPLICATE_EMAIL]}) from exc
    return user


def update_user(session: Session, user: User, changes: dict) -> User:
    changes = dict(changes)
    if "email" in changes and email_taken(
        session, changes["email"], other_than=user.id
    ):
        raise ValidationError({"email": [DUPLICATE_EMAIL]})
    if "is_active" in changes:
        set_active(session, user, changes.pop("is_active"))
    for name, value in changes.items():
        setattr(user, name, value)
    session.commit()
    return user


def _user_event_version() -> int:
    # Microseconds, not a counter, as in Django's user_events.py: these events are
    # minutes apart, and a counter on a stale user object could go backwards.
    return int(now().timestamp() * 1_000_000)


def set_active(session: Session, user: User, active: bool) -> None:
    """`instances` holds no users, so it hears of (de)activation as an event (#13).

    The caller commits.
    """
    if user.is_active == active:
        return
    user.is_active = active
    action = "reactivated" if active else "deactivated"
    events.emit(session, f"user.{action}", user.id, _user_event_version(), {})


def delete_user(session: Session, user: User) -> None:
    """Delete a user and what they own, as Django's CASCADE did, then tell `instances`.

    Like Django, this sends no per-type events: `user.deleted` covers them.
    """
    owner_id = user.id
    batteries = select(BatteryType.id).where(BatteryType.owner_id == owner_id)
    qtypes = select(QuestionnaireType.id).where(QuestionnaireType.owner_id == owner_id)
    session.execute(
        delete(BatteryTypeItem).where(
            BatteryTypeItem.battery_type_id.in_(batteries)
            | BatteryTypeItem.questionnaire_type_id.in_(qtypes)
        )
    )
    session.execute(delete(BatteryType).where(BatteryType.owner_id == owner_id))
    session.execute(
        delete(QuestionnaireType).where(QuestionnaireType.owner_id == owner_id)
    )
    clear_django_user_links(session, owner_id)
    events.emit(session, "user.deleted", owner_id, _user_event_version(), {})
    session.delete(user)
    bump_owner_generation(session, owner_id)
    session.commit()


# ── Types ──────────────────────────────────────────────────────────────────────


def owned_questionnaire_types(
    session: Session, owner_id: uuid.UUID, ids: Sequence[str]
) -> list[uuid.UUID]:
    """The ids, in order, if the owner has each of them. Otherwise a field error."""
    wanted = [uuid.UUID(i) for i in ids]
    found = set(
        session.scalars(
            select(QuestionnaireType.id).where(
                QuestionnaireType.owner_id == owner_id,
                QuestionnaireType.id.in_(wanted),
            )
        )
    )
    for raw, type_id in zip(ids, wanted, strict=True):
        if type_id not in found:
            raise ValidationError(
                {
                    "questionnaireTypeIds": [
                        f'Invalid pk "{raw}" - object does not exist.'
                    ]
                }
            )
    return wanted


def set_battery_type_items(
    session: Session, battery_type: BatteryType, questionnaire_type_ids: Sequence
) -> None:
    """Replace the battery type's ordered list of questionnaire types."""
    session.execute(
        delete(BatteryTypeItem).where(
            BatteryTypeItem.battery_type_id == battery_type.id
        )
    )
    session.add_all(
        BatteryTypeItem(
            battery_type_id=battery_type.id, questionnaire_type_id=qt_id, order=i
        )
        for i, qt_id in enumerate(questionnaire_type_ids)
    )
    session.flush()
    session.expire(battery_type, ["items"])


def save_type(session: Session, instance, *, owner_id, item_ids=None):
    """Create or update a type, with its event, in one transaction."""
    if instance.id is None:
        session.add(instance)
    else:
        instance.updated_at = now()
    session.flush()
    if item_ids is not None:
        set_battery_type_items(session, instance, item_ids)
    events.record_change(session, instance)
    bump_owner_generation(session, owner_id)
    session.commit()
    return instance


def delete_type(session: Session, instance: QuestionnaireType | BatteryType) -> None:
    """Delete a type, once `instances` has confirmed nothing there uses it.

    No database can enforce this across services, so `instances` retires its copy
    first. There the RESTRICT still guards it. Fails closed: if `instances` cannot
    answer, nothing is deleted. If this fails after a successful retire, the type
    still exists here, and the next read-through restores the copy.
    """
    if isinstance(instance, QuestionnaireType) and _in_a_battery(session, instance.id):
        raise InUse()
    try:
        instances_client().retire(events.kind_of(instance), instance.id)
    except RefInUse as exc:
        raise InUse() from exc
    except PeerUnavailable as exc:
        RETIRE_FAILURES.inc()
        raise ServiceUnavailable() from exc
    owner_id = instance.owner_id
    try:
        events.record_deleted(session, instance)
        if isinstance(instance, BatteryType):
            session.execute(
                delete(BatteryTypeItem).where(
                    BatteryTypeItem.battery_type_id == instance.id
                )
            )
        elif _in_a_battery(session, instance.id):
            # A battery type picked this type up after the check above.
            raise InUse()
        session.delete(instance)
        # So a dashboard never links to a deleted row.
        bump_owner_generation(session, owner_id)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise InUse() from exc
    except InUse:
        session.rollback()
        raise


def _in_a_battery(session: Session, type_id: uuid.UUID) -> bool:
    return bool(
        session.scalar(
            select(exists().where(BatteryTypeItem.questionnaire_type_id == type_id))
        )
    )


def clear_django_user_links(session: Session, user_id: uuid.UUID) -> None:
    """Django's group and permission links, where its tables exist (#36)."""
    connection = session.connection()
    for table in DJANGO_USER_LINKS:
        if connection.dialect.has_table(connection, table.name):
            session.execute(delete(table).where(table.c.customuser_id == user_id))
