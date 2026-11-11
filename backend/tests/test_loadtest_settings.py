"""instances' core.settings.loadtest (#9): prod over plain HTTP, private hosts only.

Each case loads the settings in a fresh interpreter, since a settings module
can only be imported once per process. catalog's loadtest profile (FastAPI, #38)
is checked in catalog/tests/test_settings.py.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

PROBE = """
import json, django
django.setup()
from django.conf import settings as s
print(json.dumps({
    "ssl_redirect": s.SECURE_SSL_REDIRECT,
    "hsts": s.SECURE_HSTS_SECONDS,
    "secure_cookies": [s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE],
    "debug": s.DEBUG,
    "engine": s.DATABASES["default"]["ENGINE"],
    "conn_max_age": s.DATABASES["default"]["CONN_MAX_AGE"],
    "conn_health_checks": s.DATABASES["default"]["CONN_HEALTH_CHECKS"],
    "loadtest": getattr(s, "LOADTEST", False),
    "signing_key": s.SIMPLE_JWT["SIGNING_KEY"],
}))
"""


def load(allowed_hosts: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, our own interpreter
        [sys.executable, "-c", PROBE],
        cwd=BACKEND / "instances",
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "core.settings.loadtest",
            "SECRET_KEY": "x" * 50,
            "JWT_VERIFYING_KEY": "public",
            "DATABASE_URL": "postgres://u:p@127.0.0.1:5432/db",
            "INSTANCES_DATABASE_URL": "postgres://u:p@127.0.0.1:5433/db",
            "CATALOG_TO_INSTANCES_TOKEN": "a",
            "INSTANCES_TO_CATALOG_TOKEN": "b",
            "CACHE_REDIS_URL": "redis://127.0.0.1:6379/1",
            "ALLOWED_HOSTS": allowed_hosts,
            **env,
        },
    )


@pytest.mark.parametrize(
    "hosts",
    [
        "localhost,127.0.0.1",
        "192.168.2.241",
        "10.0.0.5,172.16.0.1,saas-app.lan,api.internal",
    ],
)
def test_loads_with_private_hosts(hosts):
    proc = load(hosts)
    assert proc.returncode == 0, proc.stderr
    loaded = json.loads(proc.stdout)
    # It verifies tokens and cannot mint them.
    assert loaded.pop("signing_key") == ""
    assert loaded == {
        "ssl_redirect": False,
        "hsts": 0,
        "secure_cookies": [False, False],
        "debug": False,
        "engine": "django_prometheus.db.backends.postgresql",
        "conn_max_age": 60,
        "conn_health_checks": True,
        "loadtest": True,
    }


@pytest.mark.parametrize(
    "hosts", ["example.com", "localhost,8.8.8.8", "192.168.2.241,app.example.org", "*"]
)
def test_refuses_a_public_host(hosts):
    proc = load(hosts)
    assert proc.returncode != 0
    assert "core.settings.loadtest refuses ALLOWED_HOSTS" in proc.stderr


def test_selected_by_settings_env_var():
    proc = load(
        "localhost", DJANGO_SETTINGS_MODULE="core.settings", SETTINGS="loadtest"
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["loadtest"] is True


@pytest.mark.parametrize(
    "path",
    [
        "common/common/settings/base.py",
        "common/common/settings/dev.py",
        "common/common/settings/prod.py",
        "common/common/settings/test.py",
        "instances/core/settings/dev.py",
        "instances/core/settings/prod.py",
        "instances/core/settings/test.py",
    ],
)
def test_no_other_settings_module_imports_it(path):
    assert "loadtest" not in (BACKEND / path).read_text()


def test_conn_max_age_comes_from_the_environment():
    # The load-test deploy sets it per measurement (#9, Phase 6).
    proc = load("localhost", CONN_MAX_AGE="0")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["conn_max_age"] == 0


def test_instances_never_load_the_signing_key():
    proc = load("localhost", JWT_SIGNING_KEY="a-signing-key")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["signing_key"] == ""


def test_instances_refuse_a_missing_verifying_key():
    result = load("localhost", JWT_VERIFYING_KEY="")
    assert result.returncode != 0
    assert "JWT_VERIFYING_KEY" in result.stderr


def test_refuses_missing_peer_tokens():
    result = load("localhost", CATALOG_TO_INSTANCES_TOKEN="")
    assert result.returncode != 0
    assert "CATALOG_TO_INSTANCES_TOKEN" in result.stderr
