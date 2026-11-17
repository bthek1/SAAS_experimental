"""Who may call the owner API: a `catalog` access token, and an owner not blocked (#13).

`instances` has no user table. It verifies the token with the public key, then
refuses owners that a `user.*` event blocked. The SPA reacts to the 401 alone.
"""

from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from .support import create_questionnaire, new_id, token, user_event

LIST = "/api/questionnaires/"
OWNER_ENDPOINTS = [
    ("GET", "/api/questionnaires/"),
    ("POST", "/api/questionnaires/"),
    ("GET", "/api/batteries/"),
    ("GET", "/api/dashboard/"),
    ("GET", "/api/dashboard/scores/"),
    ("GET", f"/api/questionnaires/{new_id()}/"),
    ("GET", f"/api/questionnaires/{new_id()}/pdf/"),
]


def refused(response: httpx.Response) -> bool:
    return response.status_code == 401 and isinstance(response.json()["detail"], str)


def call(base_url: str, bearer: str | None, path: str = LIST) -> httpx.Response:
    headers = {"Authorization": f"Bearer {bearer}"} if bearer is not None else {}
    return httpx.get(f"{base_url}{path}", headers=headers)


@pytest.mark.parametrize(("method", "path"), OWNER_ENDPOINTS)
def test_no_token_is_401(anon, method, path):
    assert refused(anon.request(method, path))


def test_a_valid_token_needs_no_user_row(owner):
    # No such user exists anywhere: the token is all this service checks.
    response = owner.http.get(LIST)
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_another_key_is_401(base_url):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert refused(call(base_url, token(new_id(), key=other_key)))


def test_hs256_is_401(base_url):
    assert refused(call(base_url, token(new_id(), key="x" * 32, algorithm="HS256")))


def test_unsigned_is_401(base_url):
    unsigned = jwt.encode(
        {"token_type": "access", "user_id": new_id(), "jti": "x"},
        key=None,
        algorithm="none",
    )
    assert refused(call(base_url, unsigned))


def test_a_refresh_token_is_not_an_access_token(base_url):
    assert refused(call(base_url, token(new_id(), token_type="refresh")))


def test_expired_is_401(base_url):
    past = datetime.now(UTC) - timedelta(seconds=5)
    assert refused(call(base_url, token(new_id(), exp=past)))


@pytest.mark.parametrize("user_id", ["not-a-uuid", "", None])
def test_a_token_without_a_usable_owner_is_401(base_url, user_id):
    assert refused(call(base_url, token(new_id(), user_id=user_id)))


@pytest.mark.parametrize("header", ["Token {}", "Bearer", "{}", "Bearer a.b.c"])
def test_malformed_header_is_401(base_url, header):
    value = header.format(token(new_id()))
    response = httpx.get(f"{base_url}{LIST}", headers={"Authorization": value})
    assert refused(response)


def test_deactivated_owner_is_401_until_reactivated(catalog, owner):
    assert catalog.apply(user_event("deactivated", owner.id, 1)) == "applied"
    assert refused(owner.http.get(LIST))
    assert catalog.apply(user_event("reactivated", owner.id, 2)) == "applied"
    assert owner.http.get(LIST).status_code == 200


def test_an_older_deactivation_cannot_block_again(catalog, owner):
    assert catalog.apply(user_event("reactivated", owner.id, 5)) == "applied"
    assert catalog.apply(user_event("deactivated", owner.id, 4)) == "ignored"
    assert owner.http.get(LIST).status_code == 200


def test_a_repeated_event_is_ignored(catalog, owner):
    assert catalog.apply(user_event("deactivated", owner.id, 1)) == "applied"
    assert catalog.apply(user_event("deactivated", owner.id, 1)) == "ignored"


def test_blocking_one_owner_leaves_others(catalog, owner, other):
    catalog.apply(user_event("deactivated", owner.id, 1))
    assert other.http.get(LIST).status_code == 200


def test_a_deleted_owner_stays_out_whatever_arrives_late(catalog, owner):
    assert catalog.apply(user_event("deleted", owner.id, 3)) == "applied"
    assert refused(owner.http.get(LIST))
    assert catalog.apply(user_event("reactivated", owner.id, 9)) == "ignored"
    assert refused(owner.http.get(LIST))


def test_blocked_is_checked_before_the_dashboard(catalog, owner):
    # The dashboard is cached where the cache is on; a block must still win.
    assert owner.http.get("/api/dashboard/").status_code == 200
    catalog.apply(user_event("deactivated", owner.id, 1))
    assert refused(owner.http.get("/api/dashboard/"))


def test_public_endpoints_ignore_a_bad_token(base_url, catalog, owner, qtype):
    created = create_questionnaire(owner, qtype["aggregateId"])
    url = f"/api/questionnaires/by-token/{created['shareToken']}/"
    # A stale token left in a respondent's browser must not turn into a 401.
    assert call(base_url, "not-a-real-token", url).status_code == 200
    catalog.apply(user_event("deactivated", owner.id, 1))
    assert call(base_url, None, url).status_code == 200
