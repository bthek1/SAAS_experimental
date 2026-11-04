"""Applying events: duplicates, late arrivals and out-of-order delivery (#13)."""

import uuid
from datetime import UTC, datetime

import pytest
from django.core.management import call_command

from apps.catalog import events
from apps.catalog.models import QuestionnaireType

from . import refs, services
from .factories import (
    BatteryTypeFactory,
    QuestionnaireFactory,
    QuestionnaireTypeFactory,
)
from .models import BatteryTypeRef, QuestionnaireTypeRef, RetiredRef

pytestmark = pytest.mark.django_db

STAMP = datetime(2026, 1, 1, tzinfo=UTC).isoformat()


def qtype_event(owner, ref_id=None, version=1, title="T", **data):
    return {
        "id": str(uuid.uuid4()),
        "type": "questionnaire_type.changed",
        "aggregateId": str(ref_id or uuid.uuid4()),
        "version": version,
        "data": {
            "ownerId": str(owner.pk),
            "title": title,
            "questionnaireJson": data.get("questionnaire_json", {"pages": []}),
            "createdAt": STAMP,
            "updatedAt": STAMP,
        },
    }


def btype_event(owner, items, ref_id=None, version=1):
    return {
        "id": str(uuid.uuid4()),
        "type": "battery_type.changed",
        "aggregateId": str(ref_id or uuid.uuid4()),
        "version": version,
        "data": {
            "ownerId": str(owner.pk),
            "title": "B",
            "description": "",
            "createdAt": STAMP,
            "updatedAt": STAMP,
            "items": [
                {"questionnaireTypeId": str(qt_id), "order": i}
                for i, qt_id in enumerate(items)
            ],
        },
    }


def test_event_creates_the_copy_with_the_source_timestamps(user):
    event = qtype_event(user, title="PHQ", questionnaire_json={"pages": [1]})
    assert refs.apply_event(event) == refs.APPLIED
    ref = QuestionnaireTypeRef.objects.get(pk=event["aggregateId"])
    assert ref.owner_id == user.pk
    assert ref.title == "PHQ"
    assert ref.questionnaire_json == {"pages": [1]}
    assert ref.updated_at.isoformat() == STAMP
    assert ref.version == 1


def test_event_is_idempotent(user):
    event = qtype_event(user)
    assert refs.apply_event(event) == refs.APPLIED
    assert refs.apply_event(event) == refs.IGNORED
    assert QuestionnaireTypeRef.objects.count() == 1


def test_older_event_is_ignored(user):
    ref_id = uuid.uuid4()
    refs.apply_event(qtype_event(user, ref_id, version=3, title="New"))
    assert (
        refs.apply_event(qtype_event(user, ref_id, version=2, title="Old"))
        == refs.IGNORED
    )
    assert QuestionnaireTypeRef.objects.get(pk=ref_id).title == "New"


def test_newer_event_replaces_the_copy(user):
    ref_id = uuid.uuid4()
    refs.apply_event(qtype_event(user, ref_id, version=1, title="Old"))
    refs.apply_event(qtype_event(user, ref_id, version=2, title="New"))
    ref = QuestionnaireTypeRef.objects.get(pk=ref_id)
    assert (ref.title, ref.version) == ("New", 2)


def test_tombstone_blocks_late_event(user):
    ref_id = uuid.uuid4()
    refs.apply_event(qtype_event(user, ref_id, version=1))
    refs.retire_ref("questionnaire_type", ref_id)
    assert refs.apply_event(qtype_event(user, ref_id, version=2)) == refs.IGNORED
    assert not QuestionnaireTypeRef.objects.filter(pk=ref_id).exists()


def test_retiring_a_copy_that_never_arrived_still_blocks_it(user):
    ref_id = uuid.uuid4()
    refs.retire_ref("questionnaire_type", ref_id)
    assert refs.apply_event(qtype_event(user, ref_id)) == refs.IGNORED


def test_authoritative_answer_clears_the_tombstone(user):
    ref_id = uuid.uuid4()
    refs.retire_ref("questionnaire_type", ref_id)
    refs.store_snapshot(qtype_event(user, ref_id))
    assert QuestionnaireTypeRef.objects.filter(pk=ref_id).exists()
    assert not RetiredRef.objects.exists()


def test_battery_type_event_before_its_questionnaire_type(user):
    later = uuid.uuid4()
    event = btype_event(user, [later])
    refs.apply_event(event)
    battery_type = BatteryTypeRef.objects.get(pk=event["aggregateId"])
    assert [s.questionnaire_type_id for s in battery_type.slots.all()] == [later]

    # Then its questionnaire type arrives, and everything lines up.
    refs.apply_event(qtype_event(user, later))
    battery = services.create_battery(battery_type)
    assert [q.questionnaire_type_id for q in battery.questionnaires.all()] == [later]


def test_event_replaces_the_slots(user):
    ref_id, first, second = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    refs.apply_event(btype_event(user, [first, second], ref_id, version=1))
    refs.apply_event(btype_event(user, [second], ref_id, version=2))
    slots = BatteryTypeRef.objects.get(pk=ref_id).slots.all()
    assert [(s.questionnaire_type_id, s.order) for s in slots] == [(second, 0)]


def test_deleted_event_removes_the_copy(user):
    ref_id = uuid.uuid4()
    refs.apply_event(qtype_event(user, ref_id, version=1))
    deleted = {
        "type": "questionnaire_type.deleted",
        "aggregateId": str(ref_id),
        "version": 2,
        "data": {"ownerId": str(user.pk)},
    }
    assert refs.apply_event(deleted) == refs.APPLIED
    assert not QuestionnaireTypeRef.objects.filter(pk=ref_id).exists()
    assert RetiredRef.objects.filter(ref_id=ref_id).exists()


def test_deleted_event_keeps_a_copy_with_instances(user):
    qtype = QuestionnaireTypeFactory(owner=user)
    QuestionnaireFactory(questionnaire_type=qtype)
    deleted = {
        "type": "questionnaire_type.deleted",
        "aggregateId": str(qtype.pk),
        "version": qtype.version + 1,
        "data": {"ownerId": str(user.pk)},
    }
    assert refs.apply_event(deleted) == refs.IGNORED
    assert QuestionnaireTypeRef.objects.filter(pk=qtype.pk).exists()


def test_unknown_event_type_is_refused(user):
    with pytest.raises(ValueError, match="unknown event type"):
        refs.apply_event({**qtype_event(user), "type": "questionnaire.exploded"})


def test_retire_is_refused_while_instances_exist(user):
    qtype = QuestionnaireTypeFactory(owner=user)
    QuestionnaireFactory(questionnaire_type=qtype)
    with pytest.raises(refs.RefInUse):
        refs.retire_ref("questionnaire_type", qtype.pk)
    assert QuestionnaireTypeRef.objects.filter(pk=qtype.pk).exists()


def test_two_owners_events_never_cross(user, other_user):
    mine, theirs = qtype_event(user), qtype_event(other_user)
    refs.apply_event(mine)
    refs.apply_event(theirs)
    assert QuestionnaireTypeRef.objects.get(pk=mine["aggregateId"]).owner_id == user.pk
    assert (
        QuestionnaireTypeRef.objects.get(pk=theirs["aggregateId"]).owner_id
        == other_user.pk
    )


def _bump_source(source, **changes):
    QuestionnaireType.objects.filter(pk=source.pk).update(**changes)
    source.refresh_from_db()
    events.record_change(source)


def test_reconcile_repairs_every_kind_of_difference(user):
    settled = QuestionnaireTypeFactory(owner=user)
    # Stale: an edit whose event has not arrived.
    stale = QuestionnaireTypeFactory(owner=user)
    _bump_source(QuestionnaireType.objects.get(pk=stale.pk), title="Edited")
    # Missing: its copy is gone.
    missing = QuestionnaireTypeFactory(owner=user)
    QuestionnaireTypeRef.objects.filter(pk=missing.pk).delete()
    # Orphans: copies whose source is gone, one unused and one with an instance.
    orphan = QuestionnaireTypeFactory(owner=user)
    QuestionnaireType.objects.filter(pk=orphan.pk).delete()
    used = QuestionnaireTypeFactory(owner=user)
    QuestionnaireFactory(questionnaire_type=used)
    QuestionnaireType.objects.filter(pk=used.pk).delete()

    planned = refs.reconcile(dry_run=True)
    assert planned.differences == 4
    assert QuestionnaireTypeRef.objects.filter(pk=orphan.pk).exists()

    report = refs.reconcile()
    assert report.created == [f"questionnaire_type {missing.pk}"]
    assert report.updated == [f"questionnaire_type {stale.pk}"]
    assert report.removed == [f"questionnaire_type {orphan.pk}"]
    assert report.orphans_in_use == [f"questionnaire_type {used.pk}"]
    assert QuestionnaireTypeRef.objects.get(pk=stale.pk).title == "Edited"
    assert QuestionnaireTypeRef.objects.filter(pk=missing.pk).exists()
    assert not QuestionnaireTypeRef.objects.filter(pk=orphan.pk).exists()
    assert QuestionnaireTypeRef.objects.filter(pk=settled.pk).exists()

    assert refs.reconcile().differences == 1  # only the orphan in use remains


def test_reconcile_rebuilds_battery_slots(user):
    qtype = QuestionnaireTypeFactory(owner=user)
    battery_type = BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
    BatteryTypeRef.objects.filter(pk=battery_type.pk).delete()

    refs.reconcile()

    slots = BatteryTypeRef.objects.get(pk=battery_type.pk).slots.all()
    assert [s.questionnaire_type_id for s in slots] == [qtype.pk]


def test_reconcile_command(user, capsys):
    QuestionnaireTypeRef.objects.filter(
        pk=QuestionnaireTypeFactory(owner=user).pk
    ).delete()
    call_command("reconcile_refs", "--dry-run")
    assert "created: 1" in capsys.readouterr().out
    assert not QuestionnaireTypeRef.objects.exists()
