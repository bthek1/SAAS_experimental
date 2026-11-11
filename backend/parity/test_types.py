import re
import uuid

import pytest

from .conftest import CATALOG_TO_INSTANCES_TOKEN

API_TIME = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$")
EVENT_TIME = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00$")
SURVEY = {"pages": [{"name": "p1", "elements": [{"type": "text", "name": "q1"}]}]}


def create_qtype(client, title="Intake", **extra) -> dict:
    response = client.post(
        "/api/questionnaire-types/",
        json={"title": title, "questionnaireJson": SURVEY, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_battery(client, qtype_ids, title="Battery") -> dict:
    response = client.post(
        "/api/battery-types/",
        json={"title": title, "description": "d", "questionnaireTypeIds": qtype_ids},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ── Questionnaire types ────────────────────────────────────────────────────────


def test_create_questionnaire_type(client, owner):  # noqa: ARG001
    body = create_qtype(client)
    assert set(body) == {"id", "title", "questionnaireJson", "createdAt", "updatedAt"}
    uuid.UUID(body["id"])
    assert body["title"] == "Intake"
    assert body["questionnaireJson"] == SURVEY
    # DRF writes UTC as `Z`; events use isoformat()'s `+00:00` (test below).
    assert API_TIME.match(body["createdAt"])
    assert API_TIME.match(body["updatedAt"])


def test_questionnaire_json_defaults_to_empty(client, owner):  # noqa: ARG001
    response = client.post("/api/questionnaire-types/", json={"title": "Bare"})
    assert response.status_code == 201
    assert response.json()["questionnaireJson"] == {}


def test_questionnaire_type_needs_a_title(client, owner):  # noqa: ARG001
    response = client.post("/api/questionnaire-types/", json={})
    assert response.status_code == 400
    assert list(response.json()) == ["title"]


def test_title_too_long(client, owner):  # noqa: ARG001
    response = client.post("/api/questionnaire-types/", json={"title": "x" * 256})
    assert response.status_code == 400
    assert list(response.json()) == ["title"]


def test_retrieve_and_patch_questionnaire_type(client, owner):  # noqa: ARG001
    created = create_qtype(client)
    url = f"/api/questionnaire-types/{created['id']}/"
    assert client.get(url).json() == created
    response = client.patch(url, json={"title": "Renamed"})
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Renamed"
    assert body["questionnaireJson"] == SURVEY
    assert body["createdAt"] == created["createdAt"]
    assert body["updatedAt"] >= created["updatedAt"]


def test_put_is_not_allowed(client, owner):  # noqa: ARG001
    created = create_qtype(client)
    response = client.put(
        f"/api/questionnaire-types/{created['id']}/", json={"title": "x"}
    )
    assert response.status_code == 405
    assert set(response.json()) == {"detail"}


def test_types_need_a_token(client):
    assert client.get("/api/questionnaire-types/").status_code == 401
    assert client.get("/api/battery-types/").status_code == 401


def test_another_owners_type_is_not_found(client, owner, other_client):  # noqa: ARG001
    created = create_qtype(client)
    url = f"/api/questionnaire-types/{created['id']}/"
    for response in (
        other_client.get(url),
        other_client.patch(url, json={"title": "mine"}),
        other_client.delete(url),
    ):
        assert response.status_code == 404
        assert set(response.json()) == {"detail"}
    assert other_client.get("/api/questionnaire-types/").json()["count"] == 0
    assert client.get(url).json()["title"] == "Intake"


def test_unknown_id_is_not_found(client, owner):  # noqa: ARG001
    response = client.get(f"/api/questionnaire-types/{uuid.uuid4()}/")
    assert response.status_code == 404
    assert set(response.json()) == {"detail"}


# ── Battery types ──────────────────────────────────────────────────────────────


def test_create_battery_type_keeps_order(client, owner):  # noqa: ARG001
    first, second, third = (create_qtype(client, title=t)["id"] for t in "abc")
    body = create_battery(client, [third, first, second])
    assert set(body) == {
        "id",
        "title",
        "description",
        "questionnaireTypeIds",
        "createdAt",
        "updatedAt",
    }
    assert body["questionnaireTypeIds"] == [third, first, second]
    assert body["description"] == "d"
    fetched = client.get(f"/api/battery-types/{body['id']}/").json()
    assert fetched["questionnaireTypeIds"] == [third, first, second]


def test_battery_type_defaults(client, owner):  # noqa: ARG001
    response = client.post("/api/battery-types/", json={"title": "Empty"})
    assert response.status_code == 201
    body = response.json()
    assert body["description"] == ""
    assert body["questionnaireTypeIds"] == []


def test_patch_battery_items_replaces_them(client, owner):  # noqa: ARG001
    first, second = (create_qtype(client, title=t)["id"] for t in "ab")
    battery = create_battery(client, [first, second])
    url = f"/api/battery-types/{battery['id']}/"
    response = client.patch(url, json={"questionnaireTypeIds": [second]})
    assert response.status_code == 200
    assert response.json()["questionnaireTypeIds"] == [second]
    # Leaving the ids out keeps them.
    response = client.patch(url, json={"title": "Renamed"})
    assert response.json()["questionnaireTypeIds"] == [second]


def test_battery_with_another_owners_type(client, owner, other_client):  # noqa: ARG001
    foreign = create_qtype(other_client)["id"]
    response = client.post(
        "/api/battery-types/", json={"title": "B", "questionnaireTypeIds": [foreign]}
    )
    assert response.status_code == 400
    body = response.json()
    assert list(body) == ["questionnaireTypeIds"]
    assert isinstance(body["questionnaireTypeIds"][0], str)


def test_battery_with_an_unknown_type(client, owner):  # noqa: ARG001
    response = client.post(
        "/api/battery-types/",
        json={"title": "B", "questionnaireTypeIds": [str(uuid.uuid4())]},
    )
    assert response.status_code == 400
    assert list(response.json()) == ["questionnaireTypeIds"]


def test_battery_with_a_malformed_id(client, owner):  # noqa: ARG001
    response = client.post(
        "/api/battery-types/", json={"title": "B", "questionnaireTypeIds": ["nope"]}
    )
    assert response.status_code == 400
    assert list(response.json()) == ["questionnaireTypeIds"]


# ── Deleting ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", ["questionnaire-types", "battery-types"])
def test_delete(client, owner, stub, kind):  # noqa: ARG001
    created = client.post(f"/api/{kind}/", json={"title": "Gone"}).json()
    url = f"/api/{kind}/{created['id']}/"
    response = client.delete(url)
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(url).status_code == 404
    assert (kind.replace("-types", "_type"), created["id"]) in stub.retired


def test_delete_a_type_in_a_battery_is_refused(client, owner, stub):  # noqa: ARG001
    qtype = create_qtype(client)["id"]
    create_battery(client, [qtype])
    response = client.delete(f"/api/questionnaire-types/{qtype}/")
    assert response.status_code == 409
    assert set(response.json()) == {"detail"}
    assert client.get(f"/api/questionnaire-types/{qtype}/").status_code == 200
    # Refused before asking `instances`.
    assert ("questionnaire_type", qtype) not in stub.retired


def test_delete_refused_by_instances(client, owner, stub):  # noqa: ARG001
    qtype = create_qtype(client)["id"]
    stub.retire_status = 409
    response = client.delete(f"/api/questionnaire-types/{qtype}/")
    assert response.status_code == 409
    assert set(response.json()) == {"detail"}
    assert client.get(f"/api/questionnaire-types/{qtype}/").status_code == 200


@pytest.mark.parametrize("status", [500, 503, 403])
def test_delete_fails_closed_when_instances_cannot_answer(
    client,
    owner,  # noqa: ARG001
    stub,
    status,
):
    qtype = create_qtype(client)["id"]
    stub.retire_status = status
    response = client.delete(f"/api/questionnaire-types/{qtype}/")
    assert response.status_code == 503
    assert set(response.json()) == {"detail"}
    assert client.get(f"/api/questionnaire-types/{qtype}/").status_code == 200


# ── Events sent to `instances` ─────────────────────────────────────────────────


def test_writes_send_versioned_events(client, owner, stub):
    created = create_qtype(client)
    url = f"/api/questionnaire-types/{created['id']}/"
    client.patch(url, json={"title": "Two"})
    client.delete(url)
    sent = stub.events_for(created["id"])
    assert [(e["type"], e["version"]) for e in sent] == [
        ("questionnaire_type.changed", 1),
        ("questionnaire_type.changed", 2),
        ("questionnaire_type.deleted", 3),
    ]
    assert sent[1]["data"]["title"] == "Two"
    assert EVENT_TIME.match(sent[1]["data"]["createdAt"])
    assert EVENT_TIME.match(sent[1]["data"]["updatedAt"])
    assert sent[1]["data"]["ownerId"] == owner["id"]
    assert sent[2]["data"] == {"ownerId": owner["id"]}
    assert len({e["id"] for e in sent}) == 3


def test_events_carry_the_peer_token(client, owner, stub):  # noqa: ARG001
    stub.authorizations.clear()
    create_qtype(client)
    assert stub.authorizations == [f"Bearer {CATALOG_TO_INSTANCES_TOKEN}"]


def test_battery_event_carries_ordered_items(client, owner, stub):  # noqa: ARG001
    first, second = (create_qtype(client, title=t)["id"] for t in "ab")
    battery = create_battery(client, [second, first])
    (event,) = stub.events_for(battery["id"])
    assert event["data"]["items"] == [
        {"questionnaireTypeId": second, "order": 0},
        {"questionnaireTypeId": first, "order": 1},
    ]
    assert event["data"]["description"] == "d"


def test_failed_delivery_does_not_fail_the_write(client, owner, stub):  # noqa: ARG001
    stub.events_status = 500
    response = client.post("/api/questionnaire-types/", json={"title": "Queued"})
    assert response.status_code == 201
    assert stub.events_for(response.json()["id"]) == []
