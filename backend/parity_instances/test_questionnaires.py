"""The owner's questionnaires: what the SPA creates, lists, reads, renames, deletes."""

import re

import pytest

from .support import (
    TIMESTAMP,
    UUID,
    as_event,
    create_questionnaire,
    new_id,
    qtype_snapshot,
    submit,
)

LIST = "/api/questionnaires/"
FIELDS = {
    "id",
    "questionnaireTypeId",
    "questionnaireType",
    "batteryId",
    "batteryOrder",
    "name",
    "shareToken",
    "answers",
    "metrics",
    "submittedAt",
    "questionnaireJsonSnapshot",
    "createdAt",
    "updatedAt",
}
# Keys inside stored JSON are the type author's and the respondent's: never renamed.
AUTHOR_JSON = {
    "pages": [{"name": "p1", "elements": [{"type": "text", "name": "first_name"}]}],
    "calculatedValues": [{"name": "total_score", "expression": "{q1}"}],
    "snake_case": {"inner_key": [1, {"deep_key": True}]},
    "camelCase": None,
}


def detail(questionnaire_id: str) -> str:
    return f"{LIST}{questionnaire_id}/"


def test_create(catalog, owner):
    snapshot = catalog.qtype(
        owner,
        title="PHQ-9",
        questionnaire_json=AUTHOR_JSON,
        created_at="2026-01-02T03:04:05.123456+00:00",
    )
    response = owner.http.post(
        LIST, json={"questionnaireTypeId": snapshot["aggregateId"], "name": "Alice"}
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == FIELDS
    assert re.match(UUID, body["id"])
    assert re.match(UUID, body["shareToken"])
    assert body["questionnaireTypeId"] == snapshot["aggregateId"]
    assert body["name"] == "Alice"
    assert body["batteryId"] is None
    assert body["batteryOrder"] is None
    assert body["answers"] == {}
    assert body["metrics"] == {}
    assert body["submittedAt"] is None
    # Written on submit, not on create.
    assert body["questionnaireJsonSnapshot"] == {}
    assert re.match(TIMESTAMP, body["createdAt"])
    assert re.match(TIMESTAMP, body["updatedAt"])
    # The copy, in `catalog`'s type shape, with the source's timestamps.
    assert body["questionnaireType"] == {
        "id": snapshot["aggregateId"],
        "title": "PHQ-9",
        "questionnaireJson": AUTHOR_JSON,
        "createdAt": "2026-01-02T03:04:05.123456Z",
        "updatedAt": snapshot["data"]["updatedAt"].replace("+00:00", "Z"),
    }


def test_name_is_optional(owner, qtype):
    assert create_questionnaire(owner, qtype["aggregateId"])["name"] == ""


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "questionnaireTypeId"),
        ({"questionnaireTypeId": None}, "questionnaireTypeId"),
        ({"name": "x" * 256}, "name"),
    ],
)
def test_create_validation(owner, qtype, body, field):
    if field == "name":
        body = {**body, "questionnaireTypeId": qtype["aggregateId"]}
    response = owner.http.post(LIST, json=body)
    assert response.status_code == 400
    assert set(response.json()) == {field}
    assert all(isinstance(message, str) for message in response.json()[field])


def test_read_only_fields_are_ignored_on_create(owner, qtype):
    body = create_questionnaire(
        owner,
        qtype["aggregateId"],
        id=new_id(),
        answers={"q1": "forged"},
        metrics={"t": 1},
        submittedAt="2026-01-01T00:00:00Z",
        batteryId=new_id(),
        shareToken=new_id(),
    )
    assert body["answers"] == {}
    assert body["metrics"] == {}
    assert body["submittedAt"] is None
    assert body["batteryId"] is None


def test_retrieve_matches_create(owner, qtype):
    created = create_questionnaire(owner, qtype["aggregateId"], name="Bob")
    response = owner.http.get(detail(created["id"]))
    assert response.status_code == 200
    assert response.json() == created


def test_rename(owner, qtype):
    created = create_questionnaire(owner, qtype["aggregateId"])
    response = owner.http.patch(detail(created["id"]), json={"name": "Carol"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Carol"
    assert body["createdAt"] == created["createdAt"]
    assert body["updatedAt"] >= created["updatedAt"]
    assert owner.http.get(detail(created["id"])).json()["name"] == "Carol"


def test_the_owner_cannot_write_answers(owner, qtype):
    created = create_questionnaire(owner, qtype["aggregateId"])
    response = owner.http.patch(
        detail(created["id"]),
        json={"answers": {"q1": "x"}, "metrics": {"t": 1}, "submittedAt": None},
    )
    assert response.status_code == 200
    assert response.json()["answers"] == {}
    assert response.json()["metrics"] == {}


def test_the_type_cannot_change(catalog, owner, qtype):
    created = create_questionnaire(owner, qtype["aggregateId"])
    same = owner.http.patch(
        detail(created["id"]), json={"questionnaireTypeId": qtype["aggregateId"]}
    )
    assert same.status_code == 200
    other_type = catalog.qtype(owner)
    response = owner.http.patch(
        detail(created["id"]), json={"questionnaireTypeId": other_type["aggregateId"]}
    )
    assert response.status_code == 400
    assert set(response.json()) == {"questionnaireTypeId"}


def test_put_is_not_allowed(owner, qtype):
    created = create_questionnaire(owner, qtype["aggregateId"])
    body = {"questionnaireTypeId": qtype["aggregateId"], "name": "x"}
    assert owner.http.put(detail(created["id"]), json=body).status_code == 405


def test_delete(owner, qtype):
    created = create_questionnaire(owner, qtype["aggregateId"])
    response = owner.http.delete(detail(created["id"]))
    assert response.status_code == 204
    assert response.content == b""
    assert owner.http.get(detail(created["id"])).status_code == 404
    assert owner.http.delete(detail(created["id"])).status_code == 404


def test_a_submitted_questionnaire_can_be_deleted(owner, anon, qtype):
    created = create_questionnaire(owner, qtype["aggregateId"])
    submit(anon, created["shareToken"], {"q1": "a"})
    assert owner.http.delete(detail(created["id"])).status_code == 204


@pytest.mark.parametrize("path", [new_id(), "not-a-uuid"])
def test_unknown_id_is_404(owner, path):
    response = owner.http.get(detail(path))
    assert response.status_code == 404
    assert set(response.json()) == {"detail"}


# ── Owner isolation ──────────────────────────────────────────────────────────


def test_another_owners_questionnaire_is_404(owner, other, qtype):
    created = create_questionnaire(owner, qtype["aggregateId"])
    url = detail(created["id"])
    assert other.http.get(url).status_code == 404
    assert other.http.patch(url, json={"name": "x"}).status_code == 404
    assert other.http.delete(url).status_code == 404
    assert other.http.get(f"{url}pdf/").status_code == 404
    assert other.http.get(LIST).json()["count"] == 0
    assert owner.http.get(url).json()["name"] == ""


def test_another_owners_type_is_400(catalog, owner, other):
    theirs = catalog.qtype(other)
    response = owner.http.post(
        LIST, json={"questionnaireTypeId": theirs["aggregateId"]}
    )
    assert response.status_code == 400
    assert set(response.json()) == {"questionnaireTypeId"}


# ── Server-side filters (#10) ────────────────────────────────────────────────


@pytest.fixture
def mixed(catalog, owner, anon, qtype):
    other_type = catalog.qtype(owner)
    rows = {
        "open": create_questionnaire(owner, qtype["aggregateId"]),
        "done": create_questionnaire(owner, qtype["aggregateId"]),
        "other": create_questionnaire(owner, other_type["aggregateId"]),
    }
    assert submit(anon, rows["done"]["shareToken"], {"q1": "a"}).status_code == 200
    return rows


def listed(owner, **params) -> set[str]:
    response = owner.http.get(LIST, params=params)
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()["results"]}


def ids(*rows) -> set[str]:
    return {row["id"] for row in rows}


def test_filter_by_type(owner, qtype, mixed):
    found = listed(owner, questionnaireType=qtype["aggregateId"])
    assert found == ids(mixed["open"], mixed["done"])


def test_filter_by_submitted(owner, mixed):
    assert listed(owner, submitted="true") == ids(mixed["done"])
    assert listed(owner, submitted="false") == ids(mixed["open"], mixed["other"])


def test_filters_combine(owner, qtype, mixed):
    found = listed(owner, questionnaireType=qtype["aggregateId"], submitted="false")
    assert found == ids(mixed["open"])


def test_no_filter_lists_everything(owner, mixed):
    assert listed(owner) == ids(*mixed.values())


def test_filters_do_not_affect_detail(owner, qtype, mixed):
    url = detail(mixed["other"]["id"])
    response = owner.http.get(url, params={"questionnaireType": qtype["aggregateId"]})
    assert response.status_code == 200


@pytest.mark.parametrize("value", ["maybe", "2"])
def test_submitted_must_be_a_boolean(owner, value):
    response = owner.http.get(LIST, params={"submitted": value})
    assert response.status_code == 400
    assert set(response.json()) == {"submitted"}


def test_filter_by_another_owners_type_is_400(catalog, owner, other):
    theirs = catalog.qtype(other)
    response = owner.http.get(LIST, params={"questionnaireType": theirs["aggregateId"]})
    assert response.status_code == 400
    assert set(response.json()) == {"questionnaireType"}


@pytest.mark.parametrize("value", ["not-a-uuid", new_id()])
def test_filter_by_an_unknown_type_is_400(owner, value):
    response = owner.http.get(LIST, params={"questionnaireType": value})
    assert response.status_code == 400
    assert set(response.json()) == {"questionnaireType"}


def test_filter_by_a_type_not_yet_arrived_is_fetched(owner, stub):
    fresh = stub.add(qtype_snapshot(owner.id))
    response = owner.http.get(LIST, params={"questionnaireType": fresh["aggregateId"]})
    assert response.status_code == 200
    assert response.json()["count"] == 0


# ── Stored JSON is passed through as stored ──────────────────────────────────


def test_answers_metrics_and_snapshot_keep_their_keys(catalog, owner, anon):
    snapshot = catalog.qtype(owner, questionnaire_json=AUTHOR_JSON)
    created = create_questionnaire(owner, snapshot["aggregateId"])
    answers = {
        "first_name": "Ann",
        "camelKey": {"inner_key": [1, 2.5, None, {"deep_key": False}]},
        "Mixed Key": "x",
    }
    metrics = {"total_score": 7, "subScore": 2.5, "is_high": True, "band": "low"}
    assert submit(anon, created["shareToken"], answers, metrics).status_code == 200
    body = owner.http.get(detail(created["id"])).json()
    assert body["answers"] == answers
    assert body["metrics"] == metrics
    assert body["questionnaireJsonSnapshot"] == AUTHOR_JSON
    assert body["questionnaireType"]["questionnaireJson"] == AUTHOR_JSON
    assert re.match(TIMESTAMP, body["submittedAt"])
    # A later edit of the type changes the copy, never the snapshot.
    edited = qtype_snapshot(
        owner.id,
        ref_id=snapshot["aggregateId"],
        version=2,
        questionnaire_json={"pages": []},
    )
    catalog.apply(as_event(edited))
    body = owner.http.get(detail(created["id"])).json()
    assert body["questionnaireJsonSnapshot"] == AUTHOR_JSON
    assert body["questionnaireType"]["questionnaireJson"] == {"pages": []}
