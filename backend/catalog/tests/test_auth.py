import jwt
import pytest
from common.dev_keys import DEV_VERIFYING_KEY

from catalog import auth
from catalog.auth import (
    TokenError,
    authenticate,
    check_password,
    decode,
    make_password,
    must_update,
    rotate,
    token_pair,
)
from catalog.models import User
from catalog.settings import load

from .conftest import make_user


def test_hash_is_in_django_format():
    encoded = make_password("secret-pass", iterations=1000)
    algorithm, iterations, salt, _digest = encoded.split("$")
    assert (algorithm, iterations, len(salt)) == ("pbkdf2_sha256", "1000", 22)
    assert check_password("secret-pass", encoded)
    assert not check_password("other-pass", encoded)


@pytest.mark.parametrize("encoded", ["!unusable", "md5$salt$abc", "", "garbage"])
def test_foreign_or_unusable_hashes_never_match(encoded):
    assert not check_password("anything", encoded)


def test_login_upgrades_a_weak_hash(session, monkeypatch):
    user = make_user(session)
    user.password = make_password("password-123", iterations=10)
    session.commit()
    assert must_update(user.password)
    assert authenticate(session, user.email, "password-123") is user
    assert not must_update(user.password)
    assert check_password("password-123", user.password)


def test_inactive_user_cannot_log_in(session):
    user = make_user(session, is_active=False)
    assert authenticate(session, user.email, "password-123") is None


def test_token_pair_claims(user):
    pair = token_pair(user)
    access = jwt.decode(pair["access"], DEV_VERIFYING_KEY, algorithms=["RS256"])
    refresh = jwt.decode(pair["refresh"], DEV_VERIFYING_KEY, algorithms=["RS256"])
    assert list(access) == ["token_type", "exp", "iat", "jti", "user_id"]
    assert access["user_id"] == refresh["user_id"] == str(user.id)
    assert access["jti"] != refresh["jti"]


def test_decode_checks_the_type(user):
    pair = token_pair(user)
    with pytest.raises(TokenError, match="wrong type"):
        decode(pair["access"], "refresh")


def test_expired_token(user, monkeypatch):
    expired = load("test").model_copy(update={"access_token_seconds": -10})
    monkeypatch.setattr(auth, "get_settings", lambda: expired)
    access = token_pair(user)["access"]
    with pytest.raises(TokenError, match="expired"):
        decode(access, "access")


def test_rotate_keeps_the_user(user):
    _claims, access, refresh = rotate(token_pair(user)["refresh"])
    assert decode(access, "access")["user_id"] == str(user.id)
    assert decode(refresh, "refresh")["user_id"] == str(user.id)


def test_refresh_for_a_deleted_user(client, session, user):
    refresh = token_pair(user)["refresh"]
    session.delete(session.get(User, user.id))
    session.commit()
    response = client.post("/api/token/refresh/", json={"refresh": refresh})
    assert response.status_code == 401
    assert response.json()["code"] == "no_active_account"


def test_api_refuses_a_deactivated_user(auth, session, user):
    session.get(User, user.id).is_active = False
    session.commit()
    response = auth.get("/api/accounts/me/")
    assert response.status_code == 401
    assert response.json() == {"detail": "User is inactive", "code": "user_inactive"}


def test_header_with_three_parts(client):
    response = client.get("/api/accounts/me/", headers={"Authorization": "Bearer a b"})
    assert response.status_code == 401
    assert response.json()["code"] == "bad_authorization_header"


def test_unauthenticated_response_names_the_scheme(client):
    response = client.get("/api/accounts/me/")
    assert response.headers["www-authenticate"] == 'Bearer realm="api"'
