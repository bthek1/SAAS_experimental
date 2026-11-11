from pathlib import Path

import pytest
from common.dev_keys import DEV_SIGNING_KEY, DEV_VERIFYING_KEY

from catalog_fastapi.settings import ImproperlyConfigured, load

PROD_ENV = {
    "SECRET_KEY": "s",
    "ALLOWED_HOSTS": "api.example.com,.example.org",
    "CACHE_REDIS_URL": "redis://cache:6379/1",
    "DATABASE_URL": "postgres://u:p@db:5432/catalogdb",
    "CATALOG_TO_INSTANCES_TOKEN": "a",
    "INSTANCES_TO_CATALOG_TOKEN": "b",
    "JWT_SIGNING_KEY": "real-signing-key",
    "JWT_VERIFYING_KEY": "real-verifying-key",
}


@pytest.fixture
def prod_env(monkeypatch):
    for name, value in PROD_ENV.items():
        monkeypatch.setenv(name, value)
    # Only these variables: never the developer's .env.
    monkeypatch.setattr("catalog_fastapi.settings.REPO_ENV", Path("/nonexistent"))
    return monkeypatch


def test_test_profile_ignores_jwt_keys_from_the_environment(monkeypatch):
    # #33: tests sign with the dev key, so a real key in .env must not reach them.
    monkeypatch.setenv("JWT_SIGNING_KEY", "from-env")
    monkeypatch.setenv("JWT_VERIFYING_KEY", "from-env")
    settings = load("test")
    assert settings.jwt_signing_key == DEV_SIGNING_KEY
    assert settings.jwt_verifying_key == DEV_VERIFYING_KEY
    assert settings.cache_enabled is False


def test_prod_reads_comma_lists(prod_env):
    settings = load("prod")
    assert settings.allowed_hosts == ["api.example.com", ".example.org"]
    assert settings.https_redirect is True
    assert settings.sqlalchemy_url == "postgresql+psycopg://u:p@db:5432/catalogdb"


@pytest.mark.parametrize("missing", ["SECRET_KEY", "ALLOWED_HOSTS", "CACHE_REDIS_URL"])
def test_prod_requires(prod_env, missing):
    prod_env.delenv(missing)
    with pytest.raises(ImproperlyConfigured, match=missing):
        load("prod")


def test_prod_requires_peer_tokens(prod_env):
    prod_env.setenv("INSTANCES_TO_CATALOG_TOKEN", "")
    with pytest.raises(ImproperlyConfigured, match="TOKEN"):
        load("prod")


def test_prod_refuses_the_dev_key(prod_env):
    prod_env.setenv("JWT_SIGNING_KEY", DEV_SIGNING_KEY)
    with pytest.raises(ImproperlyConfigured, match="published dev key"):
        load("prod")


def test_loadtest_refuses_a_public_host(prod_env):
    with pytest.raises(ImproperlyConfigured, match=r"api\.example\.com"):
        load("loadtest")


def test_loadtest_on_private_hosts(prod_env):
    prod_env.setenv("ALLOWED_HOSTS", "192.168.2.247,saas-gateway.lan,localhost")
    settings = load("loadtest")
    assert settings.https_redirect is False
    assert settings.loadtest is True


def test_unknown_profile():
    with pytest.raises(ImproperlyConfigured, match="Unknown SETTINGS"):
        load("staging")


def test_one_line_pem_keys_get_their_newlines(prod_env):
    prod_env.setenv("JWT_SIGNING_KEY", "-----BEGIN-----\\nabc\\n-----END-----")
    assert load("prod").jwt_signing_key == "-----BEGIN-----\nabc\n-----END-----"
