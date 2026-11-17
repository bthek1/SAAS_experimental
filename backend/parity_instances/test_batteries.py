"""Batteries: one questionnaire per slot of the battery type, in slot order."""

import re

import pytest

from .support import (
    TIMESTAMP,
    UUID,
    create_battery,
    new_id,
    submit,
)

LIST = "/api/batteries/"
FIELDS = {
    "id",
    "batteryTypeId",
    "batteryTypeName",
    "name",
    "shareToken",
    "questionnaires",
    "isComplete",
    "createdAt",
    "updatedAt",
}
SLOT_FIELDS = {
    "order",
    "questionnaireId",
    "shareToken",
    "questionnaireTypeName",
    "submittedAt",
}


@pytest.fixture
def kit(catalog, owner):
    a = catalog.qtype(owner, title="A")["aggregateId"]
    b = catalog.qtype(owner, title="B")["aggregateId"]
    return catalog.btype(owner, [b, a], title="Intake"), a, b


def test_create(owner, kit):
    btype, a, b = kit
    response = owner.http.post(
        LIST, json={"batteryTypeId": btype["aggregateId"], "name": "Bob"}
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == FIELDS
    assert re.match(UUID, body["id"])
    assert re.match(UUID, body["shareToken"])
    assert body["batteryTypeId"] == btype["aggregateId"]
    assert body["batteryTypeName"] == "Intake"
    assert body["name"] == "Bob"
    assert body["isComplete"] is False
    assert re.match(TIMESTAMP, body["createdAt"])
    slots = body["questionnaires"]
    assert [set(slot) for slot in slots] == [SLOT_FIELDS, SLOT_FIELDS]
    assert [slot["order"] for slot in slots] == [0, 1]
    assert [slot["questionnaireTypeName"] for slot in slots] == ["B", "A"]
    assert [slot["submittedAt"] for slot in slots] == [None, None]

    # Each slot is an ordinary questionnaire of the owner's.
    for slot, qtype_id in zip(slots, [b, a], strict=True):
        questionnaire = owner.http.get(
            f"/api/questionnaires/{slot['questionnaireId']}/"
        ).json()
        assert questionnaire["batteryId"] == body["id"]
        assert questionnaire["batteryOrder"] == slot["order"]
        assert questionnaire["questionnaireTypeId"] == qtype_id
        assert questionnaire["shareToken"] == slot["shareToken"]
        assert questionnaire["name"] == ""


def test_retrieve_matches_create(owner, kit):
    created = create_battery(owner, kit[0]["aggregateId"])
    response = owner.http.get(f"{LIST}{created['id']}/")
    assert response.status_code == 200
    assert response.json() == created
    assert created["name"] == ""


def test_a_battery_type_with_no_slots_is_never_complete(catalog, owner):
    body = create_battery(owner, catalog.btype(owner, [])["aggregateId"])
    assert body["questionnaires"] == []
    assert body["isComplete"] is False


def test_complete_once_every_slot_is_submitted(owner, anon, kit):
    battery = create_battery(owner, kit[0]["aggregateId"])
    first, second = battery["questionnaires"]
    submit(anon, first["shareToken"])
    body = owner.http.get(f"{LIST}{battery['id']}/").json()
    assert body["isComplete"] is False
    assert re.match(TIMESTAMP, body["questionnaires"][0]["submittedAt"])
    submit(anon, second["shareToken"])
    assert owner.http.get(f"{LIST}{battery['id']}/").json()["isComplete"] is True


@pytest.mark.parametrize("method", ["PATCH", "PUT"])
def test_a_battery_cannot_be_edited(owner, kit, method):
    created = create_battery(owner, kit[0]["aggregateId"])
    response = owner.http.request(method, f"{LIST}{created['id']}/", json={"name": "x"})
    assert response.status_code == 405


def test_delete_keeps_its_questionnaires(owner, kit):
    created = create_battery(owner, kit[0]["aggregateId"])
    response = owner.http.delete(f"{LIST}{created['id']}/")
    assert response.status_code == 204
    assert owner.http.get(f"{LIST}{created['id']}/").status_code == 404
    for slot in created["questionnaires"]:
        questionnaire = owner.http.get(
            f"/api/questionnaires/{slot['questionnaireId']}/"
        )
        assert questionnaire.status_code == 200
        assert questionnaire.json()["batteryId"] is None
        assert questionnaire.json()["batteryOrder"] == slot["order"]


@pytest.mark.parametrize(
    "body", [{}, {"batteryTypeId": None}, {"batteryTypeId": "not-a-uuid"}]
)
def test_create_validation(owner, body):
    response = owner.http.post(LIST, json=body)
    assert response.status_code == 400
    assert set(response.json()) == {"batteryTypeId"}


def test_an_unknown_battery_type_is_400(owner):
    response = owner.http.post(LIST, json={"batteryTypeId": new_id()})
    assert response.status_code == 400
    assert set(response.json()) == {"batteryTypeId"}


def test_another_owners_battery_type_is_400(catalog, owner, other):
    theirs = catalog.btype(other, [])
    response = owner.http.post(LIST, json={"batteryTypeId": theirs["aggregateId"]})
    assert response.status_code == 400
    assert set(response.json()) == {"batteryTypeId"}


def test_another_owners_battery_is_404(owner, other, kit):
    created = create_battery(owner, kit[0]["aggregateId"])
    url = f"{LIST}{created['id']}/"
    assert other.http.get(url).status_code == 404
    assert other.http.delete(url).status_code == 404
    assert other.http.get(LIST).json()["count"] == 0
    assert owner.http.get(url).status_code == 200
