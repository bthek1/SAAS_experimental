"""Engine, sessions, and work that must wait for a commit (#35).

`on_commit()` is Django's `transaction.on_commit`: the outbox delivers an event and
the cache bumps a generation only once the write is durable, and never after a
rollback.
"""

import time
from collections.abc import Callable, Iterator
from functools import cache

from prometheus_client import Counter, Histogram
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .settings import get_settings

ON_COMMIT = "on_commit"
# SQLAlchemy's defaults, made explicit: app.py sizes AnyIO's thread pool to match.
POOL_SIZE = 5
POOL_OVERFLOW = 10
# django-prometheus's, so Grafana can combine these with Django's histograms.
LATENCY_BUCKETS = (
    0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0,
    2.5, 5.0, 7.5, 10.0, 25.0, 50.0, 75.0, float("inf"),
)  # fmt: skip
DB_QUERIES = Counter("db_queries_total", "SQL statements executed.")
DB_LATENCY = Histogram(
    "db_query_duration_seconds", "SQL statement latency.", buckets=LATENCY_BUCKETS
)
DB_PINGS = Counter("db_pings_total", "Idle connections checked before reuse.")
# A connection back in the pool for longer than this is pinged before reuse (#41).
PING_AFTER_IDLE = 5.0
CHECKED_IN_AT = "checked_in_at"


def _instrument(engine: Engine) -> Engine:
    @event.listens_for(engine, "before_cursor_execute")
    def _start(_conn, _cursor, _statement, _parameters, context, _many):
        context._query_started = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _stop(_conn, _cursor, _statement, _parameters, context, _many):
        DB_QUERIES.inc()
        DB_LATENCY.observe(time.perf_counter() - context._query_started)

    return engine


def _ping_idle_connections(engine: Engine) -> Engine:
    """`pool_pre_ping`, for connections that sat idle only (#41).

    `pool_pre_ping` sends `SELECT 1` on every checkout, and an authenticated request
    checks out twice (`auth.current_user` hands its connection back), so it cost two
    round trips per request. A connection reused within `PING_AFTER_IDLE` seconds
    was working a moment ago and goes out as it is. One idle longer, which is what
    a database restart or a dropped connection leaves behind, is pinged, and if
    dead the pool replaces it before the request sees it (DisconnectionError).
    """

    @event.listens_for(engine, "checkin")
    def _checked_in(_dbapi_connection, record):
        if record is not None:
            record.info[CHECKED_IN_AT] = time.monotonic()

    @event.listens_for(engine, "checkout")
    def _checkout(dbapi_connection, record, _proxy):
        checked_in = record.info.get(CHECKED_IN_AT)
        # A new connection has no CHECKED_IN_AT: it was just opened.
        if checked_in is None or time.monotonic() - checked_in < PING_AFTER_IDLE:
            return
        DB_PINGS.inc()
        try:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("SELECT 1")
            finally:
                cursor.close()
        except Exception as exc:
            raise DisconnectionError("idle connection failed its ping") from exc

    return engine


def make_engine(url: str, *, conn_max_age: int = 60) -> Engine:
    if url.startswith("sqlite"):
        options: dict = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            # One shared connection, or every session would see its own empty
            # database.
            options["poolclass"] = StaticPool
        engine = create_engine(url, **options)

        @event.listens_for(engine, "connect")
        def _foreign_keys(dbapi_connection, _record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        return _ping_idle_connections(_instrument(engine))
    engine = _instrument(
        create_engine(
            url,
            # As Django sets them on every connection. The LXC databases are
            # SQL_ASCII, where psycopg would otherwise return text as bytes.
            connect_args={"client_encoding": "utf8", "options": "-c TimeZone=UTC"},
            pool_size=POOL_SIZE,
            max_overflow=POOL_OVERFLOW,
            pool_recycle=conn_max_age if conn_max_age > 0 else -1,
        )
    )
    # A dropped connection is replaced instead of failing that request, as
    # Django's CONN_HEALTH_CHECKS does, but only after it sat idle.
    return _ping_idle_connections(engine)


@cache
def get_engine() -> Engine:
    settings = get_settings()
    return make_engine(settings.sqlalchemy_url, conn_max_age=settings.conn_max_age)


@cache
def session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed after the response."""
    with session_factory()() as session:
        yield session


def on_commit(session: Session, callback: Callable[[], object]) -> None:
    session.info.setdefault(ON_COMMIT, []).append(callback)


@event.listens_for(Session, "after_commit")
def _run_on_commit(session: Session) -> None:
    for callback in session.info.pop(ON_COMMIT, []):
        callback()


@event.listens_for(Session, "after_rollback")
def _drop_on_commit(session: Session) -> None:
    session.info.pop(ON_COMMIT, None)
