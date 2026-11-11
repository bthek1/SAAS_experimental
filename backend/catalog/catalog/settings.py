"""Configuration from the environment and the repo-root `.env` (#35).

`SETTINGS` picks a profile, as it does for `instances` (Django): dev, test, e2e,
parity, prod or loadtest. The test profiles never read `.env` and always use the
published dev JWT pair, so a developer's real keys cannot reach a test (#33).
"""

import ipaddress
import os
from functools import cache
from pathlib import Path
from typing import Annotated

from common.dev_keys import DEV_SIGNING_KEY, DEV_VERIFYING_KEY
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ENV = PACKAGE_DIR.parents[2] / ".env"
PROFILES = ("dev", "test", "e2e", "parity", "prod", "loadtest")
TEST_PROFILES = ("test", "e2e", "parity")
PRIVATE_SUFFIXES = (".lan", ".internal", ".local", ".localhost")
# Django 6.0's PBKDF2PasswordHasher.iterations. Kept equal, so hashes made by the
# Django version (until #38) are accepted without asking for an upgrade.
DJANGO_PBKDF2_ITERATIONS = 1_200_000

CommaList = Annotated[list[str], NoDecode]

# prometheus_client opens its files in this directory as metrics are created, at
# import, and every module that creates one imports this module first. gunicorn's
# on_starting hook makes the service's own, but commands (migrate, relay-outbox) run
# without gunicorn. Django's settings created it the same way.
if _multiproc_dir := os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
    Path(_multiproc_dir).mkdir(parents=True, exist_ok=True)


class ImproperlyConfigured(Exception):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    settings: str = "dev"
    debug: bool = False
    secret_key: str = ""
    database_url: str = "postgres://appuser:apppassword@localhost:5435/appdb"
    # Seconds a pooled connection is kept, as Django's CONN_MAX_AGE (#9, Phase 6).
    conn_max_age: int = 60
    allowed_hosts: CommaList = ["localhost", "127.0.0.1"]
    cors_allowed_origins: CommaList = ["http://localhost:5174"]
    cors_allowed_origin_regex: str = ""
    https_redirect: bool = False
    hsts_seconds: int = 0

    jwt_signing_key: str = ""
    jwt_verifying_key: str = ""
    access_token_seconds: int = 60 * 60
    refresh_token_seconds: int = 7 * 24 * 60 * 60
    password_iterations: int = DJANGO_PBKDF2_ITERATIONS

    catalog_to_instances_token: str = ""
    instances_to_catalog_token: str = ""
    instances_internal_url: str = "http://localhost:8007"
    peer_connect_timeout: float = 0.5
    peer_read_timeout: float = 2.0

    metrics_allowed_cidrs: CommaList = ["127.0.0.1/32", "::1/128"]
    prometheus_multiproc_dir: str = ""

    cache_enabled: bool = True
    cache_redis_url: str = "redis://localhost:6380/1"

    celery_broker_url: str = "redis://localhost:6380/0"
    celery_task_always_eager: bool = False

    # `seed-loadtest` runs only under debug or this.
    loadtest: bool = False

    @field_validator(
        "allowed_hosts", "cors_allowed_origins", "metrics_allowed_cidrs", mode="before"
    )
    @classmethod
    def _split_commas(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("jwt_signing_key", "jwt_verifying_key", mode="before")
    @classmethod
    def _pem_newlines(cls, value):
        # Env files hold a PEM key on one line, with `\n` for each newline, as
        # django-environ's `multiline` read them.
        return value.replace("\\n", "\n") if isinstance(value, str) else value

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url


def _is_private_host(host: str) -> bool:
    if host == "localhost" or host.endswith(PRIVATE_SUFFIXES):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_private
    except ValueError:
        return False


def _test_profile(profile: str, base: Settings) -> dict:
    overrides = {
        "debug": False,
        "secret_key": "test-secret",
        "database_url": "sqlite://",
        "allowed_hosts": ["localhost", "127.0.0.1", "testserver"],
        "jwt_signing_key": DEV_SIGNING_KEY,
        "jwt_verifying_key": DEV_VERIFYING_KEY,
        "catalog_to_instances_token": "test-catalog-to-instances",
        "instances_to_catalog_token": "test-instances-to-catalog",
        "metrics_allowed_cidrs": ["127.0.0.1/32", "::1/128"],
        # Fresh data in every test; cache tests turn it on.
        "cache_enabled": False,
        "celery_broker_url": "memory://",
        "celery_task_always_eager": True,
        # Hashing at full strength would dominate the suite's run time.
        "password_iterations": 1_000,
    }
    if profile == "e2e":
        overrides |= {
            "database_url": f"sqlite:///{PACKAGE_DIR.parent / 'e2e.sqlite3'}",
            "cors_allowed_origins": ["http://localhost:5184"],
            "instances_internal_url": "http://localhost:8017",
        }
    if profile == "parity":
        overrides |= {
            "database_url": f"sqlite:///{os.environ['PARITY_DATABASE']}",
            "instances_internal_url": os.environ["PARITY_INSTANCES_URL"],
        }
    return base.model_copy(update=overrides)


def _dev_profile(base: Settings) -> Settings:
    return base.model_copy(
        update={
            "debug": True,
            "secret_key": base.secret_key or "dev-secret",
            "jwt_signing_key": base.jwt_signing_key or DEV_SIGNING_KEY,
            "jwt_verifying_key": base.jwt_verifying_key or DEV_VERIFYING_KEY,
            "catalog_to_instances_token": base.catalog_to_instances_token
            or "dev-catalog-to-instances",
            "instances_to_catalog_token": base.instances_to_catalog_token
            or "dev-instances-to-catalog",
            "cors_allowed_origin_regex": r"^http://192\.168\.\d+\.\d+:\d+$",
        }
    )


def _prod_profile(base: Settings, *, loadtest: bool) -> Settings:
    # No defaults here. The cache fails open, for one, so a wrong URL would
    # otherwise run uncached with no other symptom.
    for name in ("secret_key", "allowed_hosts", "cache_redis_url", "database_url"):
        if name not in base.model_fields_set or not getattr(base, name):
            raise ImproperlyConfigured(f"Set {name.upper()}.")
    if not (base.catalog_to_instances_token and base.instances_to_catalog_token):
        raise ImproperlyConfigured(
            "Set CATALOG_TO_INSTANCES_TOKEN and INSTANCES_TO_CATALOG_TOKEN."
        )
    if not (base.jwt_signing_key and base.jwt_verifying_key):
        raise ImproperlyConfigured("Set JWT_SIGNING_KEY and JWT_VERIFYING_KEY.")
    if base.jwt_signing_key.strip() == DEV_SIGNING_KEY.strip():
        raise ImproperlyConfigured("JWT_SIGNING_KEY is the published dev key.")
    if loadtest:
        # Plain HTTP for k6 is only safe off the internet (#9).
        public = [h for h in base.allowed_hosts if not _is_private_host(h)]
        if public:
            raise ImproperlyConfigured(
                f"loadtest refuses ALLOWED_HOSTS {public}: the HTTPS redirect is "
                "off here, so it only runs behind private addresses"
            )
        return base.model_copy(update={"debug": False, "loadtest": True})
    return base.model_copy(
        update={"debug": False, "https_redirect": True, "hsts_seconds": 31_536_000}
    )


def load(profile: str | None = None) -> Settings:
    profile = profile or os.environ.get("SETTINGS", "dev")
    if profile not in PROFILES:
        raise ImproperlyConfigured(
            f"Unknown SETTINGS value: {profile!r}. Must be one of {PROFILES}."
        )
    env_file = None if profile in TEST_PROFILES or not REPO_ENV.is_file() else REPO_ENV
    base = Settings(_env_file=env_file, settings=profile)
    if profile in TEST_PROFILES:
        return _test_profile(profile, base)
    if profile == "dev":
        return _dev_profile(base)
    return _prod_profile(base, loadtest=profile == "loadtest")


@cache
def get_settings() -> Settings:
    return load()
