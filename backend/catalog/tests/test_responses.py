"""Endpoints build their JSON themselves, never through jsonable_encoder (#41)."""

import json

import pytest
from fastapi import routing

from catalog.auth import token_pair
from catalog.responses import dumps
from catalog.settings import get_settings


@pytest.fixture
def no_encoder(monkeypatch):
    """Fail any request that falls back to FastAPI's per-value walk."""

    def refuse(*_args, **_kwargs):
        raise AssertionError("an endpoint returned a value for jsonable_encoder")

    monkeypatch.setattr(routing, "jsonable_encoder", refuse)


def test_endpoints_do_not_use_jsonable_encoder(client, user, no_encoder):
    tokens = token_pair(user)
    owner = {"Authorization": f"Bearer {tokens['access']}"}
    peer = {"Authorization": f"Bearer {get_settings().instances_to_catalog_token}"}

    qtype = client.post("/api/questionnaire-types/", json={"title": "a"}, headers=owner)
    assert qtype.status_code == 201
    type_id = qtype.json()["id"]
    battery = client.post(
        "/api/battery-types/",
        json={"title": "b", "questionnaireTypeIds": [type_id]},
        headers=owner,
    )
    assert battery.status_code == 201
    battery_id = battery.json()["id"]

    calls = [
        ("get", "/api/health/", None, None, 200),
        ("get", "/internal/health/", None, None, 200),
        (
            "post",
            "/api/accounts/register/",
            None,
            {"email": "new@example.com", "password": "a-long-password-1"},
            201,
        ),
        (
            "post",
            "/api/token/",
            None,
            {"email": user.email, "password": "password-123"},
            200,
        ),
        ("post", "/api/token/refresh/", None, {"refresh": tokens["refresh"]}, 200),
        ("get", "/api/accounts/me/", owner, None, 200),
        ("patch", "/api/accounts/me/", owner, {"first_name": "Ada"}, 200),
        ("get", "/api/questionnaire-types/", owner, None, 200),
        ("get", f"/api/questionnaire-types/{type_id}/", owner, None, 200),
        ("patch", f"/api/questionnaire-types/{type_id}/", owner, {"title": "c"}, 200),
        ("get", "/api/battery-types/", owner, None, 200),
        ("get", f"/api/battery-types/{battery_id}/", owner, None, 200),
        ("patch", f"/api/battery-types/{battery_id}/", owner, {"title": "d"}, 200),
        ("get", "/internal/questionnaire-types/", peer, None, 200),
        ("get", f"/internal/questionnaire-types/{type_id}/", peer, None, 200),
    ]
    for method, path, headers, body, status in calls:
        response = client.request(method, path, headers=headers, json=body)
        assert response.status_code == status, (path, response.text)
        assert response.headers["content-type"] == "application/json", path
        response.json()


def test_bodies_are_encoded_as_starlette_encodes_them():
    # Compact separators, raw UTF-8: what JSONResponse sent before.
    assert dumps({"a": [1, "é"], "b": None}) == '{"a":[1,"é"],"b":null}'.encode()


def test_cache_hit_returns_the_stored_bytes(auth, cache_on):
    auth.post("/api/questionnaire-types/", json={"title": "a"})
    first = auth.get("/api/questionnaire-types/")
    [key] = [k for k in cache_on.data if ":type-list:" in k]
    assert cache_on.data[key] == first.content
    second = auth.get("/api/questionnaire-types/")
    assert second.content == first.content
    assert second.headers["content-type"] == "application/json"
    assert json.loads(second.content)["count"] == 1
