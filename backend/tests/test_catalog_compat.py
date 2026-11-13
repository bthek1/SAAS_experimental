"""`catalog` stays compatible with what Django made and `instances` reads (#35, #38).

Passwords keep Django's pbkdf2_sha256 format, so users created before FastAPI still log
in, and `instances` verifies tokens with simplejwt, so it must accept the ones `catalog`
mints. Django's side runs in `instances`' interpreter (catalog has no Django since
#38), each in a fresh process, as in test_jwt_settings.py.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from catalog import auth, seeding
from catalog.settings import DJANGO_PBKDF2_ITERATIONS, load

BACKEND = Path(__file__).resolve().parent.parent
PASSWORD = "compat-pass-123"


def django(service: str, script: str, **env: str) -> dict:
    result = subprocess.run(  # noqa: S603 - fixed argv, our own interpreter
        [sys.executable, "-c", f"import django; django.setup()\n{script}"],
        cwd=BACKEND / service,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "core.settings.test", **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture
def test_settings(monkeypatch):
    settings = load("test")
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    return settings


def test_iterations_match_django():
    found = django(
        "instances",
        "import json\n"
        "from django.contrib.auth.hashers import PBKDF2PasswordHasher as H\n"
        "print(json.dumps({'iterations': H.iterations}))",
    )
    assert found["iterations"] == DJANGO_PBKDF2_ITERATIONS


def test_django_accepts_a_fastapi_hash(test_settings):  # noqa: ARG001
    encoded = auth.make_password(PASSWORD, iterations=DJANGO_PBKDF2_ITERATIONS)
    found = django(
        "instances",
        "import json, sys\n"
        "from django.contrib.auth.hashers import PBKDF2PasswordHasher as H\n"
        f"print(json.dumps({{'ok': H().verify({PASSWORD!r}, {encoded!r}),"
        f" 'update': H().must_update({encoded!r})}}))",
    )
    assert found == {"ok": True, "update": False}


def test_fastapi_accepts_a_django_hash(test_settings):  # noqa: ARG001
    found = django(
        "instances",
        "import json\n"
        "from django.contrib.auth.hashers import PBKDF2PasswordHasher as H\n"
        f"print(json.dumps({{'hash': H().encode({PASSWORD!r}, H().salt())}}))",
    )
    assert auth.check_password(PASSWORD, found["hash"])
    assert not auth.check_password("wrong-password", found["hash"])


def test_instances_accepts_a_fastapi_token(test_settings):  # noqa: ARG001
    class Owner:
        id = "6f1c3c62-6f0e-4d8a-9f43-7c1f0a3b2d11"

    access = auth.token_pair(Owner)["access"]
    found = django(
        "instances",
        "import json\n"
        "from rest_framework_simplejwt.authentication import "
        "JWTStatelessUserAuthentication as A\n"
        f"token = A().get_validated_token({access.encode()!r})\n"
        "print(json.dumps({'user_id': token['user_id'], 'type': token['token_type']}))",
    )
    assert found == {"user_id": Owner.id, "type": "access"}


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
