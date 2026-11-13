"""Admin writes reach `instances` the way API writes do (#36)."""

import json

import pytest
from sqlalchemy import select

from catalog.models import BatteryType, OutboxEvent, QuestionnaireType, User
from catalog.peers import PeerUnavailable
from catalog.services import save_type

from .conftest import make_user

PASSWORD = "password-123"


def login(client, user) -> bool:
    response = client.post(
        "/admin/login",
        data={"username": user.email, "password": PASSWORD},
        follow_redirects=False,
    )
    return response.status_code == 302 and "/admin/login" not in response.headers.get(
        "location", ""
    )


@pytest.fixture
def staff(session):
    return make_user(session, is_staff=True)


@pytest.fixture
def admin(client, staff):
    assert login(client, staff)
    return client


@pytest.fixture
def qtype(session, user):
    return save_type(
        session, QuestionnaireType(owner_id=user.id, title="Q"), owner_id=user.id
    )


def test_non_staff_cannot_log_in(client, user):
    assert not login(client, user)
    assert client.get("/admin/user/list", follow_redirects=False).status_code == 302


def test_deactivated_staff_lose_access_at_once(admin, session, staff):
    assert admin.get("/admin/user/list").status_code == 200
    session.get(User, staff.id).is_active = False
    session.commit()
    assert admin.get("/admin/user/list", follow_redirects=False).status_code == 302


@pytest.mark.parametrize(
    "identity", ["user", "questionnaire-type", "battery-type", "outbox-event"]
)
def test_list_pages(admin, qtype, identity):
    assert admin.get(f"/admin/{identity}/list").status_code == 200


def test_saving_a_type_sends_one_event(admin, session, qtype, instances):
    instances.events.clear()
    response = admin.post(
        f"/admin/questionnaire-type/edit/{qtype.id}",
        data={"title": "Renamed", "questionnaire_json": json.dumps({"pages": []})},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    (event,) = instances.events
    assert (event["type"], event["version"]) == ("questionnaire_type.changed", 2)
    assert event["data"]["title"] == "Renamed"
    assert event["data"]["questionnaireJson"] == {"pages": []}


def test_deleting_an_in_use_type_is_refused(admin, session, user, qtype):
    save_type(
        session,
        BatteryType(owner_id=user.id, title="B"),
        owner_id=user.id,
        item_ids=[qtype.id],
    )
    response = admin.delete(f"/admin/questionnaire-type/delete?pks={qtype.id}")
    assert "error=This+item+is+used" in response.text
    session.expire_all()
    assert session.get(QuestionnaireType, qtype.id) is not None


def test_delete_fails_closed_when_instances_is_down(admin, session, qtype, instances):
    instances.retire_error = PeerUnavailable("down")
    response = admin.delete(f"/admin/questionnaire-type/delete?pks={qtype.id}")
    assert "error=" in response.text
    session.expire_all()
    assert session.get(QuestionnaireType, qtype.id) is not None


def test_deleting_a_type(admin, session, qtype, instances):
    type_id = qtype.id
    admin.delete(f"/admin/questionnaire-type/delete?pks={type_id}")
    session.expire_all()
    assert session.get(QuestionnaireType, type_id) is None
    assert instances.events[-1]["type"] == "questionnaire_type.deleted"


def test_deactivating_a_user_sends_the_event(admin, session, user, instances):
    response = admin.post(
        f"/admin/user/edit/{user.id}",
        data={"email": user.email, "first_name": "", "last_name": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    assert [e["type"] for e in instances.events] == ["user.deactivated"]
    session.expire_all()
    assert session.get(User, user.id).is_active is False


def test_battery_items_show_on_the_detail_page(admin, session, user, qtype):
    battery = save_type(
        session,
        BatteryType(owner_id=user.id, title="B"),
        owner_id=user.id,
        item_ids=[qtype.id],
    )
    page = admin.get(f"/admin/battery-type/details/{battery.id}")
    assert page.status_code == 200
    assert f"0: {qtype.id}" in page.text


def test_outbox_is_read_only(admin, session, qtype):
    event_id = session.scalars(select(OutboxEvent.id)).first()
    assert admin.get(f"/admin/outbox-event/details/{event_id}").status_code == 200
    for path in ("create", f"edit/{event_id}"):
        assert admin.get(f"/admin/outbox-event/{path}").status_code in {403, 404}
    admin.delete(f"/admin/outbox-event/delete?pks={event_id}")
    session.expire_all()
    assert session.get(OutboxEvent, event_id) is not None
