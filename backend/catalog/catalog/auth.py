"""Passwords and tokens, compatible with Django and simplejwt (#35).

Hashes use Django's `pbkdf2_sha256$<iterations>$<salt>$<hash>` format, so users
created by either implementation log in to the other. Tokens carry simplejwt's
claims, because `instances` verifies them with simplejwt.
"""

import base64
import hashlib
import hmac
import secrets
import string
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .db import get_session
from .errors import AuthenticationFailed, NotAuthenticated
from .models import User
from .settings import get_settings

ALGORITHM = "pbkdf2_sha256"
SALT_CHARS = string.ascii_letters + string.digits
# Django's salt: 128 bits of entropy over 62 characters.
SALT_LENGTH = 22
# Never matches a hash, so it costs the same time as a real check.
DUMMY_HASH = "pbkdf2_sha256$1000$dummysalt0000000000000$"


def _pbkdf2(password: str, salt: str, iterations: int) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return base64.b64encode(digest).decode()


def make_password(password: str, *, iterations: int | None = None) -> str:
    iterations = iterations or get_settings().password_iterations
    salt = "".join(secrets.choice(SALT_CHARS) for _ in range(SALT_LENGTH))
    return f"{ALGORITHM}${iterations}${salt}${_pbkdf2(password, salt, iterations)}"


def check_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
    except ValueError:
        # Django's unusable passwords start with "!".
        return False
    if algorithm != ALGORITHM:
        return False
    actual = _pbkdf2(password, salt, int(iterations))
    return hmac.compare_digest(actual.encode(), expected.encode())


def must_update(encoded: str) -> bool:
    """True when the hash is weaker than today's setting, as Django re-hashes."""
    parts = encoded.split("$")
    return (
        len(parts) == 4
        and parts[0] == ALGORITHM
        and int(parts[1]) < get_settings().password_iterations
    )


def authenticate(session: Session, email: str, password: str) -> User | None:
    user = session.query(User).filter_by(email=email).one_or_none()
    # Release the connection for the hash, which takes hundreds of milliseconds of
    # CPU: a burst of logins holding all 15 starved every other request (#38).
    session.commit()
    if user is None:
        check_password(password, DUMMY_HASH)
        return None
    if not check_password(password, user.password) or not user.is_active:
        return None
    if must_update(user.password):
        user.password = make_password(password)
        session.commit()
    return user


# ── Tokens ─────────────────────────────────────────────────────────────────────


class TokenError(Exception):
    pass


@lru_cache(maxsize=4)
def _signing_key(pem: str) -> RSAPrivateKey:
    # Parsing validates the RSA key, ~25 ms of CPU. Given the PEM string, PyJWT
    # parses it on every signature: a token refresh signs twice, and it took 65 ms
    # against Django's 2.8 ms on `catalog`'s own load (#39). Keyed by the PEM, so a
    # settings change still takes effect.
    key = load_pem_private_key(pem.encode(), password=None)
    if not isinstance(key, RSAPrivateKey):
        raise TypeError("JWT_SIGNING_KEY must be an RSA private key")
    return key


def _encode(claims: dict) -> str:
    key = _signing_key(get_settings().jwt_signing_key)
    return jwt.encode(claims, key, algorithm="RS256")


def _fresh(token_type: str, lifetime: int, **claims) -> dict:
    now = int(datetime.now(UTC).timestamp())
    return {
        "token_type": token_type,
        "exp": now + lifetime,
        "iat": now,
        "jti": uuid.uuid4().hex,
        **claims,
    }


def access_for(claims: dict) -> str:
    """An access token with the refresh token's own claims, as simplejwt copies."""
    own = {
        k: v for k, v in claims.items() if k not in {"token_type", "exp", "iat", "jti"}
    }
    return _encode(_fresh("access", get_settings().access_token_seconds, **own))


def token_pair(user: User) -> dict[str, str]:
    refresh = _fresh(
        "refresh", get_settings().refresh_token_seconds, user_id=str(user.id)
    )
    return {"refresh": _encode(refresh), "access": access_for(refresh)}


def decode(token: str, token_type: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_verifying_key,
            algorithms=["RS256"],
            options={"require": ["exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token is expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid") from exc
    if "jti" not in claims:
        raise TokenError("Token has no id")
    if claims.get("token_type") != token_type:
        raise TokenError("Token has wrong type")
    return claims


def rotate(refresh_token: str) -> tuple[dict, str, str]:
    """(claims, new access, new refresh). No blacklist, as configured in Django."""
    claims = decode(refresh_token, "refresh")
    settings = get_settings()
    now = int(datetime.now(UTC).timestamp())
    access = access_for(claims)
    rotated = {
        **claims,
        "jti": uuid.uuid4().hex,
        "exp": now + settings.refresh_token_seconds,
        "iat": now,
    }
    return claims, access, _encode(rotated)


def invalid_token(message: str) -> AuthenticationFailed:
    return AuthenticationFailed(
        {
            "detail": "Given token not valid for any token type",
            "code": "token_not_valid",
            "messages": [
                {
                    "token_class": "AccessToken",
                    "token_type": "access",
                    "message": message,
                }
            ],
        }
    )


def current_user(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> User:
    """simplejwt's JWTAuthentication, then DRF's IsAuthenticated."""
    header = request.headers.get("Authorization", "")
    parts = header.split()
    if not parts or parts[0] != "Bearer":
        raise NotAuthenticated()
    if len(parts) != 2:
        raise AuthenticationFailed(
            {
                "detail": "Authorization header must contain two space-delimited "
                "values",
                "code": "bad_authorization_header",
            }
        )
    try:
        claims = decode(parts[1], "access")
        user_id = uuid.UUID(str(claims["user_id"]))
    except (TokenError, KeyError, ValueError) as exc:
        raise invalid_token(str(exc) or "Token is invalid") from exc
    user = session.get(User, user_id)
    if user is None:
        raise AuthenticationFailed(
            {"detail": "User not found", "code": "user_not_found"}
        )
    if not user.is_active:
        raise AuthenticationFailed(
            {"detail": "User is inactive", "code": "user_inactive"}
        )
    # Hand the connection back before the endpoint waits for a thread, or a busy
    # worker deadlocks: every thread waits for a connection that a request waiting
    # for a thread holds (tests/test_pool_deadlock.py). expire_on_commit is off, so
    # `user` stays loaded.
    session.commit()
    return user


CurrentUser = Annotated[User, Depends(current_user)]
DbSession = Annotated[Session, Depends(get_session)]
