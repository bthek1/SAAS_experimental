"""The transactional outbox: how type changes reach `instances` (#13).

A write and its event commit together. After the commit, one delivery is tried at
once. `relay_outbox` retries whatever is left. Each event carries the full state and
a per-type `version`, so applying one is idempotent and an older one is ignored.
"""

import logging
from collections.abc import Iterator
from datetime import timedelta
from functools import partial

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.utils.peers import PeerUnavailable, instances_client

from .models import BatteryType, OutboxEvent, QuestionnaireType

logger = logging.getLogger(__name__)

MODELS = {"questionnaire_type": QuestionnaireType, "battery_type": BatteryType}
PRUNE_AFTER = timedelta(days=7)
MAX_ERROR_LENGTH = 500


def kind_of(instance: QuestionnaireType | BatteryType) -> str:
    return (
        "questionnaire_type"
        if isinstance(instance, QuestionnaireType)
        else ("battery_type")
    )


def _state(instance: QuestionnaireType | BatteryType) -> dict:
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
        state["items"] = [
            {"questionnaireTypeId": str(qt_id), "order": order}
            for qt_id, order in instance.items.order_by("order").values_list(
                "questionnaire_type_id", "order"
            )
        ]
    return state


def snapshot(instance: QuestionnaireType | BatteryType) -> dict:
    """The current state, shaped like a `changed` event."""
    kind = kind_of(instance)
    return {
        "type": f"{kind}.changed",
        "aggregateId": str(instance.pk),
        "version": instance.version,
        "data": _state(instance),
    }


def fetch_snapshot(kind: str, type_id) -> dict | None:
    instance = MODELS[kind].objects.filter(pk=type_id).first()
    return snapshot(instance) if instance else None


def iter_snapshots(kind: str) -> Iterator[dict]:
    for instance in MODELS[kind].objects.order_by("pk").iterator(chunk_size=500):
        yield snapshot(instance)


def emit(event_type: str, aggregate_id, version: int, data: dict) -> OutboxEvent:
    event = OutboxEvent.objects.create(
        event_type=event_type, aggregate_id=aggregate_id, version=version, data=data
    )
    transaction.on_commit(partial(deliver, event.pk))
    return event


@transaction.atomic
def record_change(instance: QuestionnaireType | BatteryType) -> OutboxEvent:
    """Raise the version and queue the full state. Call inside the write's transaction.

    The state is read back after taking the row lock, so concurrent writers produce
    versions in the order of the states they carry.
    """
    locked = type(instance).objects.select_for_update().get(pk=instance.pk)
    locked.version += 1
    locked.save(update_fields=["version"])
    instance.version = locked.version
    return emit(f"{kind_of(locked)}.changed", locked.pk, locked.version, _state(locked))


@transaction.atomic
def record_deleted(instance: QuestionnaireType | BatteryType) -> OutboxEvent:
    return emit(
        f"{kind_of(instance)}.deleted",
        instance.pk,
        instance.version + 1,
        {"ownerId": str(instance.owner_id)},
    )


def _attempt(event: OutboxEvent) -> None:
    """One delivery. Raises PeerUnavailable when the peer did not answer."""
    pending = OutboxEvent.objects.filter(pk=event.pk, delivered_at=None)
    try:
        instances_client().send_event(event.envelope())
    except Exception as exc:
        pending.update(
            attempts=F("attempts") + 1, last_error=str(exc)[:MAX_ERROR_LENGTH]
        )
        raise
    pending.update(
        attempts=F("attempts") + 1, delivered_at=timezone.now(), last_error=""
    )


def deliver(event_id) -> bool:
    """Try once after the commit. A failure is left for `relay_outbox`, never raised."""
    event = OutboxEvent.objects.filter(pk=event_id, delivered_at=None).first()
    if event is None:
        return False
    try:
        _attempt(event)
    except Exception as exc:
        # The write has already committed, so its response must not fail.
        logger.warning("event %s not delivered yet: %s", event_id, exc)
        return False
    return True


def deliver_pending(limit: int = 200) -> tuple[int, int]:
    """Retry undelivered events, oldest first. Returns (delivered, still pending)."""
    delivered = 0
    for event in OutboxEvent.objects.filter(delivered_at=None)[:limit]:
        try:
            _attempt(event)
        except PeerUnavailable as exc:
            # The rest would only wait for the same timeout.
            logger.warning("instances unavailable: %s", exc)
            break
        except Exception:
            # One event `instances` cannot apply must not hold up the others.
            logger.exception("event %s failed", event.pk)
        else:
            delivered += 1
    return delivered, OutboxEvent.objects.filter(delivered_at=None).count()


def prune_delivered() -> int:
    deleted, _ = OutboxEvent.objects.filter(
        delivered_at__lt=timezone.now() - PRUNE_AFTER
    ).delete()
    return deleted
