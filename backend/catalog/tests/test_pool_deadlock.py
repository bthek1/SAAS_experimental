"""A dependency must not hold a connection across the hand-off to the endpoint (#38).

Sync dependencies and sync endpoints each take a thread from AnyIO's pool (40), and
SQLAlchemy pools 15 connections per worker. When `current_user` kept its connection
after returning, a request waited for a thread while holding one. Under load every
thread was waiting for a connection, so nothing moved until the 30 s pool timeout:
the 502s at the end of `stress-20261111T080102Z`. Here, 2 threads and 1 connection.
"""

import asyncio
import time

import anyio.to_thread
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from catalog import auth, db
from catalog.app import create_app
from catalog.auth import token_pair
from catalog.models import Base

from .conftest import make_user

REQUESTS = 8


@pytest.fixture
def one_connection(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pool.sqlite3'}",
        connect_args={"check_same_thread": False},
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=3,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(db, "session_factory", lambda: factory)
    with factory() as session:
        yield token_pair(make_user(session))["access"]
    engine.dispose()


async def _concurrent_requests(token: str) -> list[int]:
    anyio.to_thread.current_default_thread_limiter().total_tokens = 2
    transport = httpx.ASGITransport(app=create_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    ) as client:
        responses = await asyncio.gather(
            *(client.get("/api/accounts/me/") for _ in range(REQUESTS))
        )
    return [response.status_code for response in responses]


def test_concurrent_requests_do_not_starve_the_pool(one_connection):
    assert asyncio.run(_concurrent_requests(one_connection)) == [200] * REQUESTS


async def _concurrent_logins(count: int) -> list[int]:
    anyio.to_thread.current_default_thread_limiter().total_tokens = 2
    transport = httpx.ASGITransport(app=create_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", timeout=30
    ) as client:
        body = {"email": "slow@example.com", "password": "password-123"}
        responses = await asyncio.gather(
            *(client.post("/api/token/", json=body) for _ in range(count))
        )
    return [response.status_code for response in responses]


def test_a_login_burst_does_not_hold_connections_through_the_hash(
    tmp_path, monkeypatch
):
    # The first stress fix held, then the read stress and the soak failed at their
    # start, as every k6 user logged in: each login kept a connection through a
    # pbkdf2 hash. 4 logins of 0.5 s on 2 threads take ~1 s; holding the single
    # connection, they would queue on it for ~2 s, past the 1 s pool timeout.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pool.sqlite3'}",
        connect_args={"check_same_thread": False},
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=1,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(db, "session_factory", lambda: factory)
    with factory() as session:
        make_user(session, "slow@example.com")
    real_check = auth.check_password

    def slow_check(password: str, encoded: str) -> bool:
        time.sleep(0.5)
        return real_check(password, encoded)

    monkeypatch.setattr(auth, "check_password", slow_check)
    try:
        assert asyncio.run(_concurrent_logins(4)) == [200] * 4
    finally:
        engine.dispose()


def test_one_thread_per_connection():
    async def limit_in_lifespan() -> float:
        app = create_app()
        async with app.router.lifespan_context(app):
            return anyio.to_thread.current_default_thread_limiter().total_tokens

    assert asyncio.run(limit_in_lifespan()) == db.POOL_SIZE + db.POOL_OVERFLOW
