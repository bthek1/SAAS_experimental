"""Everything `catalog` asks of `instances` on `/internal/` (#13). See `contracts/`.

Copies follow the rules Django's `refs.py` set (`Refs/RefService.cs` now): an event
carries a type's full state and version, a repeat or an older one is ignored, and a
retired or deleted type leaves a tombstone that no late event can undo.
"""

import json
from pathlib import Path

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
    token,
    user_event,
)

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
EVENTS = "/internal/events/"


def type_title(owner, questionnaire_id: str) -> str:
    response = owner.http.get(f"/api/questionnaires/{questionnaire_id}/")
    assert response.status_code == 200, response.text
    return response.json()["questionnaireType"]["title"]


# ── Who may call ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        f"Bearer {INSTANCES_TO_CATALOG_TOKEN}",  # the other direction's token
        "Bearer test-catalog-to-instances-but-longer",
    ],
)
def test_events_need_the_inbound_peer_token(anon, owner, authorization):
    headers = {"Authorization": authorization} if authorization else {}
    event = as_event(qtype_snapshot(owner.id))
    response = anon.post(EVENTS, json=event, headers=headers)
    assert response.status_code == 403
    assert isinstance(response.json()["detail"], str)


def test_an_owner_token_is_not_a_peer_token(anon, owner):
    headers = {"Authorization": f"Bearer {token(owner.id)}"}
    event = as_event(qtype_snapshot(owner.id))
    assert anon.post(EVENTS, json=event, headers=headers).status_code == 403
    retire = f"/internal/refs/questionnaire_type/{new_id()}/retire/"
    assert anon.post(retire, headers=headers).status_code == 403


# ── *.changed ────────────────────────────────────────────────────────────────


def test_changed_is_applied_then_a_repeat_is_ignored(catalog, owner):
    event = as_event(qtype_snapshot(owner.id, title="First"))
    response = catalog.send(event)
    assert response.status_code == 200
    assert response.json() == {"result": "applied"}
    assert catalog.send(event).json() == {"result": "ignored"}


def test_a_newer_version_replaces_the_copy(catalog, owner, stub):
    first = catalog.qtype(owner, title="First")
    created = create_questionnaire(owner, first["aggregateId"])
    newer = qtype_snapshot(
        owner.id, ref_id=first["aggregateId"], version=2, title="Second"
    )
    assert catalog.apply(as_event(newer)) == "applied"
    assert type_title(owner, created["id"]) == "Second"
    assert stub.requests == []


def test_an_older_version_is_ignored(catalog, owner):
    ref_id = new_id()
    catalog.qtype(owner, ref_id=ref_id, version=3, title="Three")
    older = qtype_snapshot(owner.id, ref_id=ref_id, version=2, title="Two")
    assert catalog.apply(as_event(older)) == "ignored"
    created = create_questionnaire(owner, ref_id)
    assert type_title(owner, created["id"]) == "Three"


def test_battery_slots_follow_the_latest_event(catalog, owner):
    a = catalog.qtype(owner, title="A")["aggregateId"]
    b = catalog.qtype(owner, title="B")["aggregateId"]
    btype = catalog.btype(owner, [a, b])
    newer = btype_snapshot(owner.id, [b, a, b], ref_id=btype["aggregateId"], version=2)
    assert catalog.apply(as_event(newer)) == "applied"
    battery = create_battery(owner, btype["aggregateId"])
    assert [slot["questionnaireTypeName"] for slot in battery["questionnaires"]] == [
        "B",
        "A",
        "B",
    ]


def test_a_battery_type_may_arrive_before_its_questionnaire_types(catalog, owner, stub):
    slot = qtype_snapshot(owner.id, title="Late")
    btype = catalog.btype(owner, [slot["aggregateId"]])
    # The slot's copy is fetched when the battery is made.
    stub.add(slot)
    battery = create_battery(owner, btype["aggregateId"])
    assert battery["questionnaires"][0]["questionnaireTypeName"] == "Late"


# ── *.deleted and retire ─────────────────────────────────────────────────────


def test_deleted_leaves_a_tombstone(catalog, owner, stub):
    snapshot = catalog.qtype(owner)
    ref_id = snapshot["aggregateId"]
    deleted = deleted_event("questionnaire_type", ref_id, owner.id, 2)
    assert catalog.apply(deleted) == "applied"
    late = qtype_snapshot(owner.id, ref_id=ref_id, version=3)
    assert catalog.apply(as_event(late)) == "ignored"
    # Gone, and `catalog` agrees.
    response = owner.http.post(
        "/api/questionnaires/", json={"questionnaireTypeId": ref_id}
    )
    assert response.status_code == 400
    assert stub.asked_for(ref_id)


def test_deleted_before_it_arrived_still_blocks_it(catalog, owner):
    ref_id = new_id()
    deleted = deleted_event("questionnaire_type", ref_id, owner.id, 2)
    assert catalog.apply(deleted) == "applied"
    late = qtype_snapshot(owner.id, ref_id=ref_id, version=1)
    assert catalog.apply(as_event(late)) == "ignored"


def test_an_older_delete_is_ignored(catalog, owner):
    snapshot = catalog.qtype(owner, version=5)
    ref_id = snapshot["aggregateId"]
    deleted = deleted_event("questionnaire_type", ref_id, owner.id, 4)
    assert catalog.apply(deleted) == "ignored"
    create_questionnaire(owner, ref_id)


def test_a_delete_of_a_type_in_use_keeps_its_instances(catalog, owner):
    snapshot = catalog.qtype(owner, title="Kept")
    created = create_questionnaire(owner, snapshot["aggregateId"])
    deleted = deleted_event("questionnaire_type", snapshot["aggregateId"], owner.id, 2)
    assert catalog.apply(deleted) == "ignored"
    assert type_title(owner, created["id"]) == "Kept"


@pytest.mark.parametrize("kind", ["questionnaire_type", "battery_type"])
def test_retire(catalog, owner, kind):
    if kind == "questionnaire_type":
        ref_id = catalog.qtype(owner)["aggregateId"]
        late = qtype_snapshot(owner.id, ref_id=ref_id, version=2)
    else:
        ref_id = catalog.btype(owner, [])["aggregateId"]
        late = btype_snapshot(owner.id, [], ref_id=ref_id, version=2)
    response = catalog.retire(kind, ref_id)
    assert response.status_code == 204
    assert response.content == b""
    # Again: still 204, nothing left to delete.
    assert catalog.retire(kind, ref_id).status_code == 204
    assert catalog.apply(as_event(late)) == "ignored"


def test_retire_of_a_type_never_seen_is_204(catalog):
    assert catalog.retire("questionnaire_type", new_id()).status_code == 204


def test_retire_of_a_questionnaire_type_in_use_is_409(catalog, owner, qtype):
    create_questionnaire(owner, qtype["aggregateId"])
    response = catalog.retire("questionnaire_type", qtype["aggregateId"])
    assert response.status_code == 409
    assert response.json() == {"detail": "in use"}
    # Still usable.
    create_questionnaire(owner, qtype["aggregateId"])


def test_retire_of_a_battery_type_in_use_is_409(catalog, owner, qtype):
    btype = catalog.btype(owner, [qtype["aggregateId"]])
    create_battery(owner, btype["aggregateId"])
    response = catalog.retire("battery_type", btype["aggregateId"])
    assert response.status_code == 409


def test_a_type_is_free_to_retire_once_its_instances_are_deleted(catalog, owner, qtype):
    created = create_questionnaire(owner, qtype["aggregateId"])
    assert owner.http.delete(f"/api/questionnaires/{created['id']}/").status_code == 204
    assert catalog.retire("questionnaire_type", qtype["aggregateId"]).status_code == 204


@pytest.mark.parametrize(
    "path",
    [
        f"/internal/refs/nonsense/{new_id()}/retire/",
        f"/internal/refs/user/{new_id()}/retire/",
        "/internal/refs/questionnaire_type/not-a-uuid/retire/",
    ],
)
def test_retire_of_an_unknown_ref_is_404(catalog, path):
    assert catalog.http.post(path).status_code == 404


def test_retire_is_post_only(catalog):
    path = f"/internal/refs/questionnaire_type/{new_id()}/retire/"
    assert catalog.http.get(path).status_code == 405


# ── Malformed events: 400, so the outbox does not retry them forever ─────────


@pytest.mark.parametrize(
    "body",
    [
        {"type": "nonsense.thing", "aggregateId": "x", "version": 1, "data": {}},
        {"type": "questionnaire_type.renamed", "version": 1, "data": {}},
        {"aggregateId": "x", "version": 1, "data": {}},
        {"type": "questionnaire_type.changed", "version": 1, "data": {}},
        [],
    ],
)
def test_a_malformed_event_is_400(catalog, body):
    response = catalog.send(body)
    assert response.status_code == 400
    assert isinstance(response.json()["detail"], str)


def test_a_body_that_is_not_json_is_400(catalog):
    response = catalog.http.post(
        EVENTS, content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400


def test_a_changed_event_missing_a_field_is_400(catalog, owner):
    event = as_event(qtype_snapshot(owner.id))
    del event["data"]["title"]
    assert catalog.send(event).status_code == 400


# ── The contract files, as `catalog` sends them ──────────────────────────────


def _contract_events() -> list[dict]:
    """Every event contract, with fresh ids that keep their relations."""
    ids: dict[str, str] = {}
    events = []
    for name in [
        "event.questionnaire_type.changed",
        "event.battery_type.changed",
        "event.battery_type.deleted",
        "event.questionnaire_type.deleted",
        "event.user.deactivated",
        "event.user.reactivated",
        "event.user.deleted",
    ]:
        text = (CONTRACTS / f"{name}.json").read_text()
        for old in {
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
            "33333333-3333-3333-3333-333333333333",
            "44444444-4444-4444-4444-444444444444",
        }:
            text = text.replace(old, ids.setdefault(old, new_id()))
        events.append(json.loads(text))
    return events


def test_every_contract_event_is_accepted(catalog):
    for event in _contract_events():
        response = catalog.send(event)
        assert response.status_code == 200, (event["type"], response.text)
        assert response.json() == {"result": "applied"}, event["type"]


# ── user.deleted ─────────────────────────────────────────────────────────────


def test_user_deleted_removes_the_owners_rows(catalog, owner, other, anon):
    qtype = catalog.qtype(owner)
    questionnaire = create_questionnaire(owner, qtype["aggregateId"])
    battery = create_battery(
        owner, catalog.btype(owner, [qtype["aggregateId"]])["aggregateId"]
    )
    theirs = create_questionnaire(other, catalog.qtype(other)["aggregateId"])

    assert catalog.apply(user_event("deleted", owner.id, 1)) == "applied"

    for path in [
        f"/api/questionnaires/by-token/{questionnaire['shareToken']}/",
        f"/api/batteries/by-token/{battery['shareToken']}/",
        f"/api/questionnaires/by-token/{battery['questionnaires'][0]['shareToken']}/",
    ]:
        assert anon.get(path).status_code == 404, path
    assert (
        anon.get(f"/api/questionnaires/by-token/{theirs['shareToken']}/").status_code
        == 200
    )
    # The copies went too, so a late event cannot bring one back.
    late = qtype_snapshot(owner.id, ref_id=qtype["aggregateId"], version=2)
    assert catalog.apply(as_event(late)) == "ignored"
    assert catalog.apply(as_event(qtype_snapshot(owner.id))) == "ignored"
