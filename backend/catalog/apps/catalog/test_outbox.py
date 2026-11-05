"""Outbox: an event commits with its write and is retried until delivered (#13)."""

import pytest
from common.peers import PeerUnavailable
from django.core.management import call_command
from django.db import transaction

from . import events
from .factories import QuestionnaireTypeFactory
from .models import OutboxEvent, QuestionnaireType

pytestmark = pytest.mark.django_db

TYPES = "/api/questionnaire-types/"
BATTERY_TYPES = "/api/battery-types/"


class Recorder:
    sent: list[dict] = []
    down = False

    def send_event(self, event):
        if Recorder.down:
            raise PeerUnavailable("instances is down")
        Recorder.sent.append(event)

    def retire(self, kind, ref_id):
        pass


class Rejecting(Recorder):
    def send_event(self, event):  # noqa: ARG002
        raise ValueError("cannot apply this")


@pytest.fixture
def recorder(settings):
    settings.INSTANCES_CLIENT = f"{__name__}.Recorder"
    Recorder.sent = []
    Recorder.down = False
    return Recorder


def test_event_commits_with_the_write(auth_client, recorder):
    response = auth_client.post(
        TYPES, {"title": "New", "questionnaireJson": {"pages": []}}, format="json"
    )
    event = OutboxEvent.objects.get()
    assert event.event_type == "questionnaire_type.changed"
    assert str(event.aggregate_id) == response.data["id"]
    assert event.version == 1
    assert event.data["title"] == "New"
    assert event.data["questionnaireJson"] == {"pages": []}
    # Inside the test's transaction: nothing has been delivered yet.
    assert event.delivered_at is None
    assert recorder.sent == []


def test_rolled_back_write_emits_nothing(
    user, recorder, django_capture_on_commit_callbacks
):
    def failing_write():
        with transaction.atomic():
            events.record_change(QuestionnaireTypeFactory(owner=user))
            raise RuntimeError("the write failed")

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(RuntimeError),
    ):
        failing_write()
    assert not OutboxEvent.objects.exists()
    assert not QuestionnaireType.objects.exists()
    assert recorder.sent == []


def test_delivered_right_after_the_commit(
    auth_client, recorder, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        auth_client.post(TYPES, {"title": "New"}, format="json")
    assert [e["type"] for e in recorder.sent] == ["questionnaire_type.changed"]
    assert OutboxEvent.objects.get().delivered_at is not None


def test_a_failed_push_does_not_fail_the_write(
    auth_client, recorder, django_capture_on_commit_callbacks
):
    recorder.down = True
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post(TYPES, {"title": "New"}, format="json")
    assert response.status_code == 201
    event = OutboxEvent.objects.get()
    assert event.delivered_at is None
    assert event.attempts == 1
    assert "instances is down" in event.last_error


def test_relay_retries_until_delivered(auth_client, recorder):
    auth_client.post(TYPES, {"title": "New"}, format="json")
    recorder.down = True
    assert events.deliver_pending() == (0, 1)
    assert OutboxEvent.objects.get().attempts == 1

    recorder.down = False
    assert events.deliver_pending() == (1, 0)
    assert [e["data"]["title"] for e in recorder.sent] == ["New"]
    # A delivered event is never sent again.
    assert events.deliver_pending() == (0, 0)
    assert len(recorder.sent) == 1


def test_one_bad_event_does_not_hold_up_the_rest(auth_client, settings):
    settings.INSTANCES_CLIENT = f"{__name__}.Rejecting"
    auth_client.post(TYPES, {"title": "One"}, format="json")
    auth_client.post(TYPES, {"title": "Two"}, format="json")
    assert events.deliver_pending() == (0, 2)
    assert list(OutboxEvent.objects.values_list("attempts", flat=True)) == [1, 1]


def test_relay_command(auth_client, recorder, capsys):  # noqa: ARG001
    auth_client.post(TYPES, {"title": "New"}, format="json")
    call_command("relay_outbox", "--once")
    assert "delivered: 1, pending: 0" in capsys.readouterr().out


def test_relay_keeps_going_until_stopped(auth_client, recorder, capsys, mocker):
    recorder.down = True
    auth_client.post(TYPES, {"title": "New"}, format="json")
    # The first pass fails and the second delivers. The third sleep ends the test.
    sleep = mocker.patch(
        "apps.catalog.management.commands.relay_outbox.time.sleep",
        side_effect=[None, KeyboardInterrupt],
    )
    mocker.patch.object(
        events,
        "prune_delivered",
        side_effect=lambda: setattr(recorder, "down", False),
    )

    with pytest.raises(KeyboardInterrupt):
        call_command("relay_outbox", "--interval", "9")

    assert sleep.call_args.args == (9.0,)
    output = capsys.readouterr().out
    assert "delivered: 0, pending: 1" in output
    assert "delivered: 1, pending: 0" in output


def test_deliver_skips_an_event_already_delivered(auth_client, recorder):
    auth_client.post(TYPES, {"title": "New"}, format="json")
    event = OutboxEvent.objects.get()
    events.deliver_pending()
    assert events.deliver(event.pk) is False
    assert len(recorder.sent) == 1


def test_every_write_raises_the_version(auth_client, recorder):  # noqa: ARG001
    created = auth_client.post(TYPES, {"title": "A"}, format="json").data
    auth_client.patch(f"{TYPES}{created['id']}/", {"title": "B"}, format="json")
    assert QuestionnaireType.objects.get(pk=created["id"]).version == 2
    assert list(
        OutboxEvent.objects.order_by("version").values_list("version", "data__title")
    ) == [(1, "A"), (2, "B")]


def test_battery_type_event_carries_its_items_in_order(auth_client, user, recorder):  # noqa: ARG001
    first = QuestionnaireTypeFactory(owner=user)
    second = QuestionnaireTypeFactory(owner=user)
    auth_client.post(
        BATTERY_TYPES,
        {"title": "B", "questionnaireTypeIds": [str(second.pk), str(first.pk)]},
        format="json",
    )
    event = OutboxEvent.objects.get(event_type="battery_type.changed")
    assert event.data["items"] == [
        {"questionnaireTypeId": str(second.pk), "order": 0},
        {"questionnaireTypeId": str(first.pk), "order": 1},
    ]


def test_snapshot_never_raises_the_version(user):
    qtype = QuestionnaireTypeFactory(owner=user)
    assert events.fetch_snapshot("questionnaire_type", qtype.pk)["version"] == 0
    assert events.fetch_snapshot("questionnaire_type", user.pk) is None
