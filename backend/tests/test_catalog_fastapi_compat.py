"""The FastAPI `catalog` and the Django services accept each other's secrets (#35).

Users made by either implementation must log in to the other, so a switch back is a
config change. And `instances` verifies tokens with simplejwt, so it must accept the
ones the FastAPI `catalog` mints. Each Django side runs in its own interpreter, as
in test_jwt_settings.py.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from catalog_fastapi import auth, seeding
from catalog_fastapi.settings import DJANGO_PBKDF2_ITERATIONS, load

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
        "catalog",
        "import json\n"
        "from django.contrib.auth.hashers import PBKDF2PasswordHasher as H\n"
        "print(json.dumps({'iterations': H.iterations}))",
    )
    assert found["iterations"] == DJANGO_PBKDF2_ITERATIONS


def test_django_accepts_a_fastapi_hash(test_settings):  # noqa: ARG001
    encoded = auth.make_password(PASSWORD, iterations=DJANGO_PBKDF2_ITERATIONS)
    found = django(
        "catalog",
        "import json, sys\n"
        "from django.contrib.auth.hashers import PBKDF2PasswordHasher as H\n"
        f"print(json.dumps({{'ok': H().verify({PASSWORD!r}, {encoded!r}),"
        f" 'update': H().must_update({encoded!r})}}))",
    )
    assert found == {"ok": True, "update": False}


def test_fastapi_accepts_a_django_hash(test_settings):  # noqa: ARG001
    found = django(
        "catalog",
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


def test_seed_ids_match_django():
    # `instances` seeds from the copies these ids reach, so they must not move.
    probe = (
        "import json\n"
        "from apps.catalog.seeding import _id, owner_email\n"
        "owner = _id(owner_email(3))\n"
        "print(json.dumps([str(owner), str(_id(owner, 'scale', 2)),"
        " str(_id(owner, 'battery'))]))"
    )
    owner = seeding._id(seeding.owner_email(3))
    ours = [
        str(owner),
        str(seeding._id(owner, "scale", 2)),
        str(seeding._id(owner, "battery")),
    ]
    assert django("catalog", probe) == ours
