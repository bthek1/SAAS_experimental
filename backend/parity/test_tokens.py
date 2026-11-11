"""`instances` verifies these tokens with simplejwt, so their claims are a contract."""

import jwt
from common.dev_keys import DEV_VERIFYING_KEY

from .conftest import PASSWORD, login, register

ACCESS_SECONDS = 60 * 60
REFRESH_SECONDS = 7 * 24 * 60 * 60


def decode(token: str) -> dict:
    return jwt.decode(token, DEV_VERIFYING_KEY, algorithms=["RS256"])


def test_obtain_returns_access_and_refresh(client):
    user = register(client)
    tokens = login(client, user["email"])
    assert set(tokens) == {"access", "refresh"}
    assert jwt.get_unverified_header(tokens["access"])["alg"] == "RS256"


def test_access_claims(client):
    user = register(client)
    claims = decode(login(client, user["email"])["access"])
    assert set(claims) == {"token_type", "exp", "iat", "jti", "user_id"}
    assert claims["token_type"] == "access"
    assert claims["user_id"] == user["id"]
    assert claims["exp"] - claims["iat"] == ACCESS_SECONDS


def test_refresh_claims(client):
    user = register(client)
    claims = decode(login(client, user["email"])["refresh"])
    assert set(claims) == {"token_type", "exp", "iat", "jti", "user_id"}
    assert claims["token_type"] == "refresh"
    assert claims["exp"] - claims["iat"] == REFRESH_SECONDS


def test_wrong_password(client):
    user = register(client)
    response = client.post(
        "/api/token/", json={"email": user["email"], "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert set(response.json()) == {"detail"}


def test_unknown_email(client):
    response = client.post(
        "/api/token/", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert response.status_code == 401
    assert set(response.json()) == {"detail"}


def test_obtain_missing_fields(client):
    response = client.post("/api/token/", json={})
    assert response.status_code == 400
    assert set(response.json()) == {"email", "password"}


def test_refresh_rotates(client):
    user = register(client)
    tokens = login(client, user["email"])
    response = client.post("/api/token/refresh/", json={"refresh": tokens["refresh"]})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access", "refresh"}
    assert body["refresh"] != tokens["refresh"]
    assert decode(body["access"])["user_id"] == user["id"]
    # No blacklist: the old refresh token still works until it expires.
    again = client.post("/api/token/refresh/", json={"refresh": tokens["refresh"]})
    assert again.status_code == 200


def test_refresh_rejects_an_access_token(client):
    user = register(client)
    access = login(client, user["email"])["access"]
    response = client.post("/api/token/refresh/", json={"refresh": access})
    assert response.status_code == 401
    assert response.json()["code"] == "token_not_valid"


def test_refresh_rejects_garbage(client):
    response = client.post("/api/token/refresh/", json={"refresh": "garbage"})
    assert response.status_code == 401
    body = response.json()
    assert set(body) == {"detail", "code"}
    assert body["code"] == "token_not_valid"


def test_access_token_works_on_the_api(client):
    user = register(client)
    access = login(client, user["email"])["access"]
    response = client.get(
        "/api/accounts/me/", headers={"Authorization": f"Bearer {access}"}
    )
    assert response.status_code == 200
