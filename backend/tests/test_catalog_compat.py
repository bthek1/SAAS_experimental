"""`catalog` stays compatible with what Django made and `instances` reads (#35-#45).

Passwords keep Django's pbkdf2_sha256 format, so users created before FastAPI still log
in. Django's side is frozen here: no service has run Django since #45 removed it from
`instances`, at `6b47566`. Tokens must carry the claims simplejwt did, which
`instances` (`Auth/OwnerAuth.cs`) checks; `frontend/e2e/integration` sends `catalog`'s
tokens to it for real.
"""

import jwt
import pytest
from common.dev_keys import DEV_VERIFYING_KEY

from catalog import auth, seeding
from catalog.settings import DJANGO_PBKDF2_ITERATIONS, load

PASSWORD = "compat-pass-123"

# Django 6.0's PBKDF2PasswordHasher, frozen by #45: its iteration count, and
# `encode(PASSWORD, DJANGO_SALT)`.
DJANGO_ITERATIONS = 1_200_000
DJANGO_SALT = "frozensalt0123456789ab"
DJANGO_HASH = (
    "pbkdf2_sha256$1200000$frozensalt0123456789ab$"
    "UbZqRmwtllG9MsBQrvHW7JE+YhzoFvDUXbJIbMDgH3o="
)


@pytest.fixture
def test_settings(monkeypatch):
    settings = load("test")
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    return settings


def test_iterations_match_django():
    assert DJANGO_PBKDF2_ITERATIONS == DJANGO_ITERATIONS


def test_hashes_like_django():
    # The same password and salt give Django's hash, so Django would accept ours.
    digest = auth._pbkdf2(PASSWORD, DJANGO_SALT, DJANGO_ITERATIONS)
    assert f"pbkdf2_sha256${DJANGO_ITERATIONS}${DJANGO_SALT}${digest}" == DJANGO_HASH
    encoded = auth.make_password(PASSWORD, iterations=DJANGO_PBKDF2_ITERATIONS)
    algorithm, iterations, salt, _ = encoded.split("$")
    assert (algorithm, int(iterations), len(salt)) == ("pbkdf2_sha256", 1_200_000, 22)


def test_fastapi_accepts_a_django_hash(test_settings):  # noqa: ARG001
    assert auth.check_password(PASSWORD, DJANGO_HASH)
    assert not auth.check_password("wrong-password", DJANGO_HASH)


def test_access_tokens_carry_what_instances_checks(test_settings):  # noqa: ARG001
    class Owner:
        id = "6f1c3c62-6f0e-4d8a-9f43-7c1f0a3b2d11"

    access = auth.token_pair(Owner)["access"]
    claims = jwt.decode(access, DEV_VERIFYING_KEY, algorithms=["RS256"])
    assert jwt.get_unverified_header(access)["alg"] == "RS256"
    assert claims["token_type"] == "access"
    assert claims["user_id"] == Owner.id
    assert {"exp", "iat", "jti"} <= claims.keys()


# From Django's `apps.catalog.seeding` for owner 3, frozen when #38 removed it
# (still at `edb8acd`). `instances` seeds from the copies these ids reach, so they
# must not move.
DJANGO_SEED_IDS = [
    "281b18f8-9635-572f-8295-a6225af14c99",
    "78ab98f9-7f26-505b-a983-af16928639cb",
    "21cb459d-ea78-59ba-a2d6-0c42e8927983",
]


def test_seed_ids_match_django():
    owner = seeding._id(seeding.owner_email(3))
    ours = [
        str(owner),
        str(seeding._id(owner, "scale", 2)),
        str(seeding._id(owner, "battery")),
    ]
    assert ours == DJANGO_SEED_IDS
