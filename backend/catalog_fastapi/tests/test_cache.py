"""Cached type lists: per owner, invalidated by writes, fail open (#11)."""

import json

from prometheus_client import REGISTRY

from catalog_fastapi.auth import token_pair

from .conftest import make_user


def cache_count(result: str) -> float:
    value = REGISTRY.get_sample_value(
        "app_cache_requests_total", {"group": "type-list", "result": result}
    )
    return value or 0


def test_second_read_is_a_hit(auth, cache_on):
    auth.post("/api/questionnaire-types/", json={"title": "a"})
    hits = cache_count("hit")
    first = auth.get("/api/questionnaire-types/").json()
    second = auth.get("/api/questionnaire-types/").json()
    assert first == second
    assert cache_count("hit") == hits + 1


def test_values_are_json(auth, cache_on):
    auth.post("/api/questionnaire-types/", json={"title": "a"})
    auth.get("/api/questionnaire-types/")
    entries = [k for k in cache_on.data if ":type-list:" in k]
    assert entries
    assert json.loads(cache_on.data[entries[0]])["count"] == 1


def test_a_write_invalidates(auth, cache_on):
    auth.post("/api/questionnaire-types/", json={"title": "a"})
    assert auth.get("/api/questionnaire-types/").json()["count"] == 1
    auth.post("/api/questionnaire-types/", json={"title": "b"})
    assert auth.get("/api/questionnaire-types/").json()["count"] == 2


def test_two_owners_never_share_a_value(client, session, cache_on):
    tokens = []
    for title in ("mine", "theirs"):
        owner = make_user(session)
        token = token_pair(owner)["access"]
        tokens.append(token)
        client.post(
            "/api/questionnaire-types/",
            json={"title": title},
            headers={"Authorization": f"Bearer {token}"},
        )
    titles = [
        client.get(
            "/api/questionnaire-types/", headers={"Authorization": f"Bearer {t}"}
        ).json()["results"][0]["title"]
        for t in tokens
    ]
    assert titles == ["mine", "theirs"]


def test_redis_down_still_serves(auth, cache_on):
    auth.post("/api/questionnaire-types/", json={"title": "a"})
    cache_on.down = True
    errors = cache_count("error")
    response = auth.get("/api/questionnaire-types/")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert cache_count("error") == errors + 1


def test_a_bad_page_is_not_cached(auth, cache_on):
    auth.post("/api/questionnaire-types/", json={"title": "a"})
    assert auth.get("/api/questionnaire-types/?page=9").status_code == 404
    assert not [k for k in cache_on.data if ":type-list:" in k]
