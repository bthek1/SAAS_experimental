"""The transactional outbox: how type changes reach `instances` (#13, #35).

A write and its event commit together. After the commit, one delivery is tried at
once. `relay-outbox` retries whatever is left. Each event carries the full state and
a per-type `version`, so applying one is idempotent and an older one is ignored.
"""

import logging
import uuid
from datetime import timedelta
from functools import partial

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .db import on_commit, session_factory
from .models import BatteryType, BatteryTypeItem, OutboxEvent, QuestionnaireType, now
from .peers import PeerUnavailable, instances_client

logger = logging.getLogger(__name__)

MODELS: dict[str, type[QuestionnaireType] | type[BatteryType]] = {
    "questionnaire_type": QuestionnaireType,
    "battery_type": BatteryType,
}
PRUNE_AFTER = timedelta(days=7)
MAX_ERROR_LENGTH = 500

TypeRow = QuestionnaireType | BatteryType


def kind_of(instance: TypeRow) -> str:
    return (
        "questionnaire_type"
        if isinstance(instance, QuestionnaireType)
        else "battery_type"
    )


def _state(session: Session, instance: TypeRow) -> dict:
    state = {
        "ownerId": str(instance.owner_id),
        "title": instance.title,
        "createdAt": instance.created_at.isoformat(),
        "updatedAt": instance.updated_at.isoformat(),
    }
    if isinstance(instance, QuestionnaireType):
        state["questionnaireJson"] = instance.questionnaire_json
    else:
        state["description"] = instance.description
        rows = session.execute(
            select(BatteryTypeItem.questionnaire_type_id, BatteryTypeItem.order)
            .where(BatteryTypeItem.battery_type_id == instance.id)
            .order_by(BatteryTypeItem.order)
        )
        state["items"] = [
            {"questionnaireTypeId": str(qt_id), "order": order} for qt_id, order in rows
        ]
    return state


def snapshot(session: Session, instance: TypeRow) -> dict:
    """The current state, shaped like a `changed` event."""
    return {
        "type": f"{kind_of(instance)}.changed",
        "aggregateId": str(instance.id),
        "version": instance.version,
        "data": _state(session, instance),
    }


def fetch_snapshot(session: Session, kind: str, type_id: uuid.UUID) -> dict | None:
    instance = session.get(MODELS[kind], type_id)
    return snapshot(session, instance) if instance else None


def snapshot_page(
    session: Session, kind: str, *, after: uuid.UUID | None, limit: int
) -> list[dict]:
    model = MODELS[kind]
    query = select(model).order_by(model.id).limit(limit)
    if after:
        query = query.where(model.id > after)
    return [snapshot(session, row) for row in session.scalars(query)]


def emit(
    session: Session, event_type: str, aggregate_id, version: int, data: dict
) -> OutboxEvent:
    event = OutboxEvent(
        event_type=event_type, aggregate_id=aggregate_id, version=version, data=data
    )
    session.add(event)
    session.flush()
    on_commit(session, partial(deliver, event.id))
    return event


def record_change(session: Session, instance: TypeRow) -> OutboxEvent:
    """Raise the version and queue the full state. Call inside the write's transaction.

    The state is read back after taking the row lock, so concurrent writers produce
    versions in the order of the states they carry.
    """
    session.flush()
    model = type(instance)
    locked = session.scalars(
        select(model)
        .where(model.id == instance.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    locked.version += 1
    session.flush()
    return emit(
        session,
        f"{kind_of(locked)}.changed",
        locked.id,
        locked.version,
        _state(session, locked),
    )


def record_deleted(session: Session, instance: TypeRow) -> OutboxEvent:
    return emit(
        session,
        f"{kind_of(instance)}.deleted",
        instance.id,
        instance.version + 1,
        {"ownerId": str(instance.owner_id)},
    )


def _attempt(session: Session, event: OutboxEvent) -> None:
    """One delivery. Raises PeerUnavailable when the peer did not answer."""
    pending = (
        update(OutboxEvent)
        .where(OutboxEvent.id == event.id, OutboxEvent.delivered_at.is_(None))
        .execution_options(synchronize_session=False)
    )
    try:
        instances_client().send_event(event.envelope())
    except Exception as exc:
        session.execute(
            pending.values(
                attempts=OutboxEvent.attempts + 1,
                last_error=str(exc)[:MAX_ERROR_LENGTH],
            )
        )
        session.commit()
        raise
    session.execute(
        pending.values(
            attempts=OutboxEvent.attempts + 1, delivered_at=now(), last_error=""
        )
    )
    session.commit()


def deliver(event_id: uuid.UUID) -> bool:
    """Try once after the commit. A failure is left for `relay-outbox`, never raised."""
    with session_factory()() as session:
        event = session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.id == event_id, OutboxEvent.delivered_at.is_(None)
            )
        ).one_or_none()
        if event is None:
            return False
        try:
            _attempt(session, event)
        except Exception as exc:
            # The write has already committed, so its response must not fail.
            logger.warning("event %s not delivered yet: %s", event_id, exc)
            return False
        return True


def deliver_pending(session: Session, limit: int = 200) -> tuple[int, int]:
    """Retry undelivered events, oldest first. Returns (delivered, still pending)."""
    delivered = 0
    events = session.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.delivered_at.is_(None))
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(limit)
    ).all()
    for event in events:
        try:
            _attempt(session, event)
        except PeerUnavailable as exc:
            # The rest would only wait for the same timeout.
            logger.warning("instances unavailable: %s", exc)
            break
        except Exception:
            # One event `instances` cannot apply must not hold up the others.
            logger.exception("event %s failed", event.id)
        else:
            delivered += 1
    remaining = session.scalar(
        select(func.count()).where(OutboxEvent.delivered_at.is_(None))
    )
    return delivered, remaining or 0


def prune_delivered(session: Session) -> int:
    result = session.execute(
        delete(OutboxEvent).where(OutboxEvent.delivered_at < now() - PRUNE_AFTER)
    )
    session.commit()
    return result.rowcount
