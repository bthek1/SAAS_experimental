"""Pooled connections are pinged only after sitting idle (#41)."""

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import text

from catalog import db


def pings() -> float:
    return REGISTRY.get_sample_value("db_pings_total") or 0


@pytest.fixture
def engine(tmp_path):
    # A file database, so the pool keeps real connections between checkouts.
    engine = db.make_engine(f"sqlite:///{tmp_path / 'pool.sqlite3'}")
    yield engine
    engine.dispose()


def query(engine) -> int:
    with engine.connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one()


def test_a_busy_connection_is_not_pinged(engine, monkeypatch):
    monkeypatch.setattr(db, "PING_AFTER_IDLE", 60.0)
    before = pings()
    for _ in range(5):
        query(engine)
    assert pings() == before


def test_an_idle_connection_is_pinged(engine, monkeypatch):
    query(engine)
    monkeypatch.setattr(db, "PING_AFTER_IDLE", 0.0)
    before = pings()
    query(engine)
    assert pings() == before + 1


def test_a_new_connection_is_not_pinged(engine, monkeypatch):
    monkeypatch.setattr(db, "PING_AFTER_IDLE", 0.0)
    before = pings()
    query(engine)
    assert pings() == before


def test_a_dead_idle_connection_is_replaced(engine, monkeypatch):
    with engine.connect() as connection:
        first = connection.connection.dbapi_connection
        connection.execute(text("SELECT 1"))
    # As if the server dropped it while it sat in the pool.
    first.close()
    monkeypatch.setattr(db, "PING_AFTER_IDLE", 0.0)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
        assert connection.connection.dbapi_connection is not first
