"""What `instances` may ask of `catalog` over /internal/ (backend/contracts/)."""

import uuid

import pytest

from .contracts import assert_same_shape, contract, shape

KINDS = [
    ("questionnaire-types", "questionnaire_type"),
    ("battery-types", "battery_type"),
]


def test_health_needs_no_token(client):
    response = client.get("/internal/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("token", [None, "Bearer wrong", "test-instances-to-catalog"])
def test_snapshots_need_the_peer_token(client, token):
    headers = {"Authorization": token} if token else {}
    response = client.get("/internal/questionnaire-types/", headers=headers)
    assert response.status_code == 403
    assert set(response.json()) == {"detail"}


def test_questionnaire_type_snapshot(client, owner, internal):
    created = client.post(
        "/api/questionnaire-types/", json={"title": "Q", "questionnaireJson": {"a": 1}}
    ).json()
    client.patch(f"/api/questionnaire-types/{created['id']}/", json={"title": "Q2"})
    response = internal.get(f"/internal/questionnaire-types/{created['id']}/")
    assert response.status_code == 200
    body = response.json()
    assert_same_shape(body, "response.questionnaire_type", "questionnaireJson")
    assert body["type"] == "questionnaire_type.changed"
    assert body["aggregateId"] == created["id"]
    assert body["version"] == 2
    assert body["data"]["title"] == "Q2"
    assert body["data"]["ownerId"] == owner["id"]
    assert body["data"]["questionnaireJson"] == {"a": 1}


def test_battery_type_snapshot(client, owner, internal):  # noqa: ARG001
    qtype = client.post("/api/questionnaire-types/", json={"title": "Q"}).json()
    battery = client.post(
        "/api/battery-types/",
        json={"title": "B", "questionnaireTypeIds": [qtype["id"]]},
    ).json()
    body = internal.get(f"/internal/battery-types/{battery['id']}/").json()
    assert_same_shape(body, "response.battery_type")
    assert body["data"]["items"] == [{"questionnaireTypeId": qtype["id"], "order": 0}]
    assert body["version"] == 1


@pytest.mark.parametrize(("slug", "_kind"), KINDS)
def test_unknown_snapshot(internal, slug, _kind):
    response = internal.get(f"/internal/{slug}/{uuid.uuid4()}/")
    assert response.status_code == 404
    assert set(response.json()) == {"detail"}


def test_malformed_id_is_not_found(internal):
    assert internal.get("/internal/questionnaire-types/nope/").status_code == 404


@pytest.mark.parametrize(("slug", "kind"), KINDS)
def test_snapshot_pages_by_id(client, owner, internal, slug, kind):  # noqa: ARG001
    for i in range(3):
        client.post(f"/api/{slug}/", json={"title": f"t{i}"})
    body = internal.get(f"/internal/{slug}/").json()
    assert set(body) == {"results", "next"}
    ids = [row["aggregateId"] for row in body["results"]]
    # The suite shares one database, so other tests' rows are here too.
    assert body["next"] == (ids[-1] if len(ids) == 500 else None)
    assert ids == sorted(ids)
    assert all(row["type"] == f"{kind}.changed" for row in body["results"])

    after = ids[len(ids) // 2]
    rest = internal.get(f"/internal/{slug}/", params={"after": after}).json()
    assert [row["aggregateId"] for row in rest["results"]] == [
        i for i in ids if i > after
    ]


def test_type_page_shape(client, owner, internal):  # noqa: ARG001
    client.post(
        "/api/questionnaire-types/", json={"title": "Q", "questionnaireJson": {"a": 1}}
    )
    body = internal.get("/internal/questionnaire-types/").json()
    page = {"results": body["results"][:1], "next": None}
    expected = contract("response.type_page")
    for row in (*page["results"], *expected["results"]):
        row["data"].pop("questionnaireJson")
    assert shape(page) == shape(expected)
