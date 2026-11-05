"""Admin writes reach `instances` the same way API writes do (#13)."""

import pytest
from common.peers import PeerUnavailable, RefInUse
from django.contrib.messages import get_messages

from .factories import BatteryTypeFactory, QuestionnaireTypeFactory, UserFactory
from .models import BatteryType, OutboxEvent, QuestionnaireType

pytestmark = pytest.mark.django_db

QTYPE_ADMIN = "/admin/catalog/questionnairetype/"
BTYPE_ADMIN = "/admin/catalog/batterytype/"


class FakeInstances:
    raises: Exception | None = None

    def send_event(self, event):
        pass

    def retire(self, kind, ref_id):  # noqa: ARG002
        if FakeInstances.raises is not None:
            raise FakeInstances.raises


@pytest.fixture(autouse=True)
def instances(settings):
    settings.INSTANCES_CLIENT = f"{__name__}.FakeInstances"
    FakeInstances.raises = None
    return FakeInstances


@pytest.fixture
def staff(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    return client


def test_adding_a_type_records_an_event(staff, user):
    response = staff.post(
        f"{QTYPE_ADMIN}add/",
        {"owner": user.pk, "title": "From admin", "questionnaire_json": "{}"},
    )

    assert response.status_code == 302
    qtype = QuestionnaireType.objects.get(title="From admin")
    event = OutboxEvent.objects.get(aggregate_id=qtype.pk)
    assert event.event_type == "questionnaire_type.changed"
    assert event.data["title"] == "From admin"


def test_editing_a_type_raises_the_version(staff, user):
    qtype = QuestionnaireTypeFactory(owner=user)
    before = qtype.version

    staff.post(
        f"{QTYPE_ADMIN}{qtype.pk}/change/",
        {"owner": user.pk, "title": "Renamed", "questionnaire_json": "{}"},
    )

    qtype.refresh_from_db()
    assert qtype.version == before + 1
    event = OutboxEvent.objects.filter(aggregate_id=qtype.pk).latest("version")
    assert (event.version, event.data["title"]) == (qtype.version, "Renamed")


def test_a_battery_types_event_carries_the_items_saved_with_it(staff, user):
    """The event is recorded after the inlines, or it would miss them."""
    qtype = QuestionnaireTypeFactory(owner=user)

    staff.post(
        f"{BTYPE_ADMIN}add/",
        {
            "owner": user.pk,
            "title": "Bundle",
            "description": "",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-questionnaire_type": qtype.pk,
            "items-0-order": "0",
        },
    )

    btype = BatteryType.objects.get(title="Bundle")
    event = OutboxEvent.objects.get(aggregate_id=btype.pk)
    assert event.data["items"] == [{"questionnaireTypeId": str(qtype.pk), "order": 0}]


def test_delete_goes_through_the_retire_check(staff, user):
    qtype = QuestionnaireTypeFactory(owner=user)

    response = staff.post(f"{QTYPE_ADMIN}{qtype.pk}/delete/", {"post": "yes"})

    assert response.status_code == 302
    assert not QuestionnaireType.objects.filter(pk=qtype.pk).exists()
    assert OutboxEvent.objects.filter(
        aggregate_id=qtype.pk, event_type="questionnaire_type.deleted"
    ).exists()


@pytest.mark.parametrize(
    ("raises", "message"),
    [
        (PeerUnavailable("down"), "unavailable"),
        (RefInUse(), "used by existing"),
    ],
)
def test_a_refused_delete_keeps_the_type_and_explains(
    staff, user, instances, raises, message
):
    qtype = QuestionnaireTypeFactory(owner=user)
    instances.raises = raises

    response = staff.post(f"{QTYPE_ADMIN}{qtype.pk}/delete/", {"post": "yes"})

    assert response.status_code == 302
    assert response.url == f"{QTYPE_ADMIN}{qtype.pk}/change/"
    assert QuestionnaireType.objects.filter(pk=qtype.pk).exists()
    assert message in " ".join(str(m) for m in get_messages(response.wsgi_request))


@pytest.mark.parametrize("url", [QTYPE_ADMIN, BTYPE_ADMIN])
def test_the_bulk_delete_action_is_gone(staff, url):
    """It would skip the check with `instances`."""
    response = staff.get(url)
    assert "delete_selected" not in response.context["cl"].model_admin.get_actions(
        response.wsgi_request
    )


def test_a_battery_type_delete_is_checked_too(staff, user, instances):
    btype = BatteryTypeFactory(owner=user)
    instances.raises = PeerUnavailable("down")

    staff.post(f"{BTYPE_ADMIN}{btype.pk}/delete/", {"post": "yes"})

    assert BatteryType.objects.filter(pk=btype.pk).exists()


def test_the_outbox_is_read_only(staff, user):
    qtype = QuestionnaireTypeFactory(owner=user)
    event = OutboxEvent.objects.create(
        event_type="questionnaire_type.changed",
        aggregate_id=qtype.pk,
        version=1,
        data={},
    )

    assert staff.get("/admin/catalog/outboxevent/").status_code == 200
    assert staff.get("/admin/catalog/outboxevent/add/").status_code == 403
    staff.post(
        f"/admin/catalog/outboxevent/{event.pk}/change/",
        {"event_type": "edited", "aggregate_id": qtype.pk, "version": 9, "data": "{}"},
    )
    event.refresh_from_db()
    assert event.event_type == "questionnaire_type.changed"
