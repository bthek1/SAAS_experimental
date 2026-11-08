"""Test settings use the dev JWT pair whatever `.env` holds (#33).

Tests sign tokens with DEV_SIGNING_KEY, so a developer's own key in `.env` once
turned five `instances` tests into 401s. Each case loads the settings in a fresh
interpreter, since a settings module can only be imported once per process.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from common.dev_keys import DEV_SIGNING_KEY, DEV_VERIFYING_KEY
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

BACKEND = Path(__file__).resolve().parent.parent

PROBE = """
import json, django
django.setup()
from django.conf import settings as s
print(json.dumps({k: s.SIMPLE_JWT[k] for k in ("SIGNING_KEY", "VERIFYING_KEY")}))
"""


def other_pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private, public


def jwt_keys(service: str, settings: str, **env: str) -> dict:
    result = subprocess.run(  # noqa: S603 - fixed argv, our own interpreter
        [sys.executable, "-c", PROBE],
        cwd=BACKEND / service,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": settings, **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def other_keys() -> dict:
    private, public = other_pair()
    return {"JWT_SIGNING_KEY": private, "JWT_VERIFYING_KEY": public}


@pytest.mark.parametrize("service", ["catalog", "instances"])
def test_test_settings_ignore_keys_in_the_environment(service, other_keys):
    keys = jwt_keys(service, "core.settings.test", **other_keys)
    assert keys["VERIFYING_KEY"].strip() == DEV_VERIFYING_KEY.strip()
    if service == "catalog":
        assert keys["SIGNING_KEY"].strip() == DEV_SIGNING_KEY.strip()
    else:
        assert keys["SIGNING_KEY"] == ""


def test_dev_settings_still_read_keys_from_the_environment(other_keys):
    keys = jwt_keys("instances", "core.settings.dev", **other_keys)
    assert keys["VERIFYING_KEY"].strip() == other_keys["JWT_VERIFYING_KEY"].strip()
