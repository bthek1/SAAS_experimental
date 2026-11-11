import os

# Before any import of the package: settings are read once, on first use.
os.environ["SETTINGS"] = "test"

import uuid

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from catalog_fastapi import cache, peers
from catalog_fastapi.app import create_app
from catalog_fastapi.auth import token_pair
from catalog_fastapi.db import get_engine, session_factory
from catalog_fastapi.models import Base, User
from catalog_fastapi.services import create_user
from catalog_fastapi.settings import get_settings


class RecordingInstances:
    """The peer under test: records events, answers retire as told."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.retired: list[tuple[str, str]] = []
        self.fail_events: Exception | None = None
        self.retire_error: Exception | None = None

    def send_event(self, event: dict) -> None:
        if self.fail_events:
            raise self.fail_events
        self.events.append(event)

    def retire(self, kind: str, ref_id) -> None:
        if self.retire_error:
            raise self.retire_error
        self.retired.append((kind, str(ref_id)))


class FakeRedis:
    """The few commands cache.py uses. `down` makes every call fail."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.down = False

    def _check(self) -> None:
        if self.down:
            raise RedisError("connection refused")

    def get(self, key: str):
        self._check()
        return self.data.get(key)

    def set(self, key: str, value, ex=None, nx=False):
        self._check()
        if nx and key in self.data:
            return None
        self.data[key] = value.encode() if isinstance(value, str) else value
        return True


@pytest.fixture(autouse=True)
def database():
    engine = get_engine()
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def instances():
    fake = RecordingInstances()
    previous = peers.set_instances_client(fake)
    yield fake
    peers.set_instances_client(previous)


@pytest.fixture
def session():
    with session_factory()() as db_session:
        yield db_session


@pytest.fixture
def client():
    with TestClient(create_app(), base_url="http://testserver") as test_client:
        yield test_client


def make_user(session, email: str | None = None, **fields) -> User:
    return create_user(
        session,
        email or f"u-{uuid.uuid4().hex[:8]}@example.com",
        "password-123",
        **fields,
    )


@pytest.fixture
def user(session):
    return make_user(session)


@pytest.fixture
def auth(client, user):
    """The client, sending `user`'s access token."""
    client.headers["Authorization"] = f"Bearer {token_pair(user)['access']}"
    return client


@pytest.fixture
def cache_on(monkeypatch):
    """A working cache, in memory. Tests can set `.down = True`."""
    fake = FakeRedis()
    settings = get_settings().model_copy(update={"cache_enabled": True})
    monkeypatch.setattr(cache, "get_settings", lambda: settings)
    monkeypatch.setattr(cache, "client", lambda: fake)
    return fake
