"""The outbox: events commit with their write and are delivered after it (#13)."""

from datetime import timedelta

from sqlalchemy import select

from catalog import events
from catalog.metrics import RETIRE_FAILURES
from catalog.models import OutboxEvent, QuestionnaireType, now
from catalog.peers import PeerUnavailable
from catalog.services import save_type


def new_type(session, user, title="T") -> QuestionnaireType:
    return save_type(
        session, QuestionnaireType(owner_id=user.id, title=title), owner_id=user.id
    )


def pending(session) -> list[OutboxEvent]:
    session.expire_all()
    return list(
        session.scalars(select(OutboxEvent).where(OutboxEvent.delivered_at.is_(None)))
    )


def test_write_delivers_after_commit(session, user, instances):
    qtype = new_type(session, user)
    (event,) = instances.events
    assert (event["type"], event["version"]) == ("questionnaire_type.changed", 1)
    assert event["aggregateId"] == str(qtype.id)
    assert pending(session) == []


def test_rollback_sends_nothing(session, user, instances):
    qtype = QuestionnaireType(owner_id=user.id, title="never")
    session.add(qtype)
    session.flush()
    events.record_change(session, qtype)
    session.rollback()
    assert instances.events == []
    assert session.scalars(select(OutboxEvent)).all() == []


def test_versions_count_up(session, user, instances):
    qtype = new_type(session, user)
    qtype.title = "Two"
    save_type(session, qtype, owner_id=user.id)
    assert [e["version"] for e in instances.events] == [1, 2]
    assert instances.events[1]["data"]["title"] == "Two"


def test_failed_delivery_stays_pending(session, user, instances):
    instances.fail_events = PeerUnavailable("down")
    new_type(session, user)
    (event,) = pending(session)
    assert event.attempts == 1
    assert "down" in event.last_error


def test_deliver_pending_retries(session, user, instances):
    instances.fail_events = PeerUnavailable("down")
    new_type(session, user, "a")
    new_type(session, user, "b")
    instances.fail_events = None
    assert events.deliver_pending(session) == (2, 0)
    assert [e["data"]["title"] for e in instances.events] == ["a", "b"]


def test_deliver_pending_stops_when_the_peer_is_down(session, user, instances):
    instances.fail_events = PeerUnavailable("down")
    for title in "abc":
        new_type(session, user, title)
    assert events.deliver_pending(session) == (0, 3)
    # One attempt from the commit, one from the relay, and the relay stopped there.
    assert sorted(e.attempts for e in pending(session)) == [1, 1, 2]


def test_one_bad_event_does_not_hold_up_the_rest(session, user, instances):
    instances.fail_events = ValueError("event refused: HTTP 400")
    new_type(session, user, "a")
    new_type(session, user, "b")
    assert events.deliver_pending(session) == (0, 2)
    assert all(e.attempts == 2 for e in pending(session))


def test_prune_delivered(session, user):
    new_type(session, user)
    (event,) = session.scalars(select(OutboxEvent)).all()
    event.delivered_at = now() - timedelta(days=8)
    session.commit()
    assert events.prune_delivered(session) == 1


def test_snapshot_page_orders_by_id(session, user):
    for title in "abc":
        new_type(session, user, title)
    page = events.snapshot_page(session, "questionnaire_type", after=None, limit=2)
    ids = [row["aggregateId"] for row in page]
    assert ids == sorted(ids)
    assert len(ids) == 2


def test_retire_failure_is_counted(auth, session, user, instances):
    qtype = new_type(session, user)
    instances.retire_error = PeerUnavailable("down")
    before = RETIRE_FAILURES._value.get()
    response = auth.delete(f"/api/questionnaire-types/{qtype.id}/")
    assert response.status_code == 503
    assert RETIRE_FAILURES._value.get() == before + 1
    assert session.get(QuestionnaireType, qtype.id) is not None
