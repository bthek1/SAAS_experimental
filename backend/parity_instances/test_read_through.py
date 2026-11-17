"""A type used before its event arrives, and what `catalog` being down costs (#13).

A synchronous answer from `catalog` is authoritative: it stores the copy and clears a
tombstone. `catalog` unreachable is a 503 (the id may well be valid); `catalog`
saying 404 is a 400 on the field.
"""

import re

import pytest

from .support import (
    INSTANCES_TO_CATALOG_TOKEN,
    as_event,
    btype_snapshot,
    create_battery,
    create_questionnaire,
    deleted_event,
    new_id,
    qtype_snapshot,
    submit,
)

UNAVAILABLE = "This action is temporarily unavailable. Please try again."


def post_questionnaire(owner, ref_id: str):
    return owner.http.post("/api/questionnaires/", json={"questionnaireTypeId": ref_id})


def read_throughs(anon) -> dict[str, float]:
    found = re.findall(
        r'^app_ref_read_through_total\{result="(\w+)"\} (\S+)$',
        anon.get("/metrics").text,
        re.MULTILINE,
    )
    return {result: float(value) for result, value in found}


def test_a_type_not_yet_arrived_is_fetched(owner, stub):
    snapshot = stub.add(qtype_snapshot(owner.id, title="Fresh"))
    response = post_questionnaire(owner, snapshot["aggregateId"])
    assert response.status_code == 201, response.text
    assert response.json()["questionnaireType"]["title"] == "Fresh"
    (request,) = stub.requests
    assert request.path == f"/internal/questionnaire-types/{snapshot['aggregateId']}/"
    assert request.authorization == f"Bearer {INSTANCES_TO_CATALOG_TOKEN}"
    # Stored: the next use does not ask again.
    post_questionnaire(owner, snapshot["aggregateId"])
    assert len(stub.requests) == 1


def test_a_battery_type_not_yet_arrived_is_fetched_with_its_slots(owner, stub):
    slot = stub.add(qtype_snapshot(owner.id, title="Slot"))
    btype = stub.add(btype_snapshot(owner.id, [slot["aggregateId"]], title="Kit"))
    battery = create_battery(owner, btype["aggregateId"])
    assert battery["batteryTypeName"] == "Kit"
    assert [q["questionnaireTypeName"] for q in battery["questionnaires"]] == ["Slot"]
    assert any("/internal/battery-types/" in r.path for r in stub.requests)


def test_an_authoritative_answer_clears_a_tombstone(catalog, owner, stub):
    """`catalog` failed after the retire: the type exists, so the owner can use it."""
    snapshot = catalog.qtype(owner)
    ref_id = snapshot["aggregateId"]
    assert catalog.retire("questionnaire_type", ref_id).status_code == 204
    stub.add(qtype_snapshot(owner.id, ref_id=ref_id, version=2, title="Back"))
    response = post_questionnaire(owner, ref_id)
    assert response.status_code == 201
    assert response.json()["questionnaireType"]["title"] == "Back"
    # No tombstone left: newer events apply again.
    newer = qtype_snapshot(owner.id, ref_id=ref_id, version=3, title="Newer")
    assert catalog.apply(as_event(newer)) == "applied"


def test_catalog_404_is_a_field_error(owner, stub):
    response = post_questionnaire(owner, new_id())
    assert response.status_code == 400
    assert set(response.json()) == {"questionnaireTypeId"}
    assert isinstance(response.json()["questionnaireTypeId"][0], str)
    assert len(stub.requests) == 1


@pytest.mark.parametrize("mode", ["500", "down"])
def test_catalog_unavailable_is_503(owner, stub, mode):
    stub.mode = mode
    response = post_questionnaire(owner, new_id())
    assert response.status_code == 503
    assert response.json() == {"detail": UNAVAILABLE}


@pytest.mark.parametrize("mode", ["500", "down"])
def test_a_battery_type_unavailable_is_503(owner, stub, mode):
    stub.mode = mode
    response = owner.http.post("/api/batteries/", json={"batteryTypeId": new_id()})
    assert response.status_code == 503


def test_another_owners_type_from_catalog_is_400(owner, other, stub):
    theirs = stub.add(qtype_snapshot(other.id))
    response = post_questionnaire(owner, theirs["aggregateId"])
    assert response.status_code == 400
    assert set(response.json()) == {"questionnaireTypeId"}


def test_another_owners_copy_is_400_without_asking(catalog, owner, other, stub):
    theirs = catalog.qtype(other)
    stub.mode = "down"
    response = post_questionnaire(owner, theirs["aggregateId"])
    assert response.status_code == 400
    assert stub.requests == []


# Not an integer: Django reads one as UUID(int=...), which no client sends.
@pytest.mark.parametrize("value", ["not-a-uuid", "", None])
def test_a_malformed_id_is_400_without_asking(owner, stub, value):
    stub.mode = "down"
    response = owner.http.post(
        "/api/questionnaires/", json={"questionnaireTypeId": value}
    )
    assert response.status_code == 400
    assert set(response.json()) == {"questionnaireTypeId"}
    assert stub.requests == []


def test_a_known_type_needs_no_catalog(owner, qtype, stub):
    stub.mode = "down"
    assert post_questionnaire(owner, qtype["aggregateId"]).status_code == 201
    assert stub.requests == []


def test_the_whole_hot_path_needs_no_catalog(catalog, owner, anon, qtype, stub):
    """The point of the copies: `catalog` can be down for all of this."""
    btype = catalog.btype(owner, [qtype["aggregateId"]])
    stub.mode = "down"
    created = create_questionnaire(owner, qtype["aggregateId"])
    create_battery(owner, btype["aggregateId"])
    url = f"/api/questionnaires/by-token/{created['shareToken']}/"
    assert anon.get(url).status_code == 200
    assert submit(anon, created["shareToken"], {"q1": "a"}, {"t": 1}).status_code == 200
    assert owner.http.get("/api/questionnaires/").status_code == 200
    assert owner.http.get("/api/batteries/").status_code == 200
    assert owner.http.get("/api/dashboard/").status_code == 200
    scores = owner.http.get(
        "/api/dashboard/scores/", params={"questionnaireType": qtype["aggregateId"]}
    )
    assert scores.status_code == 200
    assert stub.requests == []


def test_a_battery_slot_catalog_no_longer_has_is_503(catalog, owner):
    btype = catalog.btype(owner, [new_id()])
    response = owner.http.post(
        "/api/batteries/", json={"batteryTypeId": btype["aggregateId"]}
    )
    assert response.status_code == 503
    # Nothing half-made.
    assert owner.http.get("/api/batteries/").json()["count"] == 0
    assert owner.http.get("/api/questionnaires/").json()["count"] == 0


def test_a_deleted_type_is_not_fetched_back_by_events(catalog, owner, stub):
    ref_id = new_id()
    catalog.apply(deleted_event("questionnaire_type", ref_id, owner.id, 2))
    # `catalog` still answers (a delete that failed): the answer wins.
    stub.add(qtype_snapshot(owner.id, ref_id=ref_id, version=1))
    assert post_questionnaire(owner, ref_id).status_code == 201


def test_read_throughs_are_counted_by_result(anon, owner, stub):
    before = read_throughs(anon)
    fresh = stub.add(qtype_snapshot(owner.id))
    assert post_questionnaire(owner, fresh["aggregateId"]).status_code == 201
    assert post_questionnaire(owner, new_id()).status_code == 400
    stub.mode = "down"
    assert post_questionnaire(owner, new_id()).status_code == 503
    after = read_throughs(anon)
    for result in ("found", "missing", "unavailable"):
        assert after.get(result, 0) == before.get(result, 0) + 1, result
