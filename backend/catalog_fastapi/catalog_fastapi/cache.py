"""Server-side cache for expensive reads, as `common/cache.py` (#11, #35).

The same rules: `owner_id` is required, `group` is from a fixed list (it is a
Prometheus label), Redis errors are counted and the value computed (fail open), and
each owner has a random generation in every key, replaced after a commit to make
their entries unreachable without scanning.

Two differences. Values are JSON, not pickle, so writing to this Redis cannot run
code here. And keys have their own prefix, so this service never reads entries the
Django version stored.
"""

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from functools import cache
from typing import Any
from uuid import UUID

import redis
from prometheus_client import Counter
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from .db import on_commit
from .settings import get_settings

logger = logging.getLogger(__name__)

PREFIX = "catalog-fastapi"
GENERATION = "generation"
CACHE_GROUPS = frozenset({"type-list"})

CACHE_REQUESTS = Counter(
    "app_cache_requests_total",
    "Cached reads by group and result (hit, miss, error).",
    ["group", "result"],
)


@cache
def client() -> redis.Redis:
    # Short timeouts bound how long a failing Redis can hold up a request.
    return redis.Redis.from_url(
        get_settings().cache_redis_url,
        socket_connect_timeout=0.1,
        socket_timeout=0.1,
    )


def _generation_key(owner_id: UUID | str) -> str:
    return f"{PREFIX}:generation:{owner_id}"


def _entry_key(
    group: str, owner_id: UUID | str, generation: str, params: dict, version: int
) -> str:
    encoded = json.dumps(params, sort_keys=True, default=str).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{PREFIX}:{group}:v{version}:{owner_id}:{generation}:{digest}"


def _record_error(group: str, operation: str, exc: RedisError) -> None:
    CACHE_REQUESTS.labels(group=group, result="error").inc()
    logger.warning("cache %s failed for %s: %s", operation, group, exc)


def _generation(owner_id: UUID | str) -> str:
    redis_client = client()
    key = _generation_key(owner_id)
    redis_client.set(key, uuid.uuid4().hex, nx=True)
    value = redis_client.get(key)
    return value.decode() if isinstance(value, bytes) else str(value)


def cached[T](
    group: str,
    *,
    owner_id: UUID | str,
    params: dict,
    ttl: int,
    compute: Callable[[], T],
    version: int = 1,
) -> T:
    """The cached value for this owner and params, or compute and store it.

    `compute` must return JSON-serialisable data. Bump `version` when its shape
    changes. An exception from `compute` propagates and stores nothing.
    """
    if group not in CACHE_GROUPS:
        raise ValueError(f"unknown cache group {group!r}: add it to CACHE_GROUPS")
    if not get_settings().cache_enabled:
        return compute()

    try:
        key = _entry_key(group, owner_id, _generation(owner_id), params, version)
        raw: Any = client().get(key)
    except RedisError as exc:
        _record_error(group, "read", exc)
        return compute()

    if raw is not None:
        CACHE_REQUESTS.labels(group=group, result="hit").inc()
        return json.loads(raw)

    CACHE_REQUESTS.labels(group=group, result="miss").inc()
    value = compute()
    try:
        client().set(key, json.dumps(value), ex=ttl)
    except RedisError as exc:
        _record_error(group, "write", exc)
    return value


def bump_owner_generation(session: Session, owner_id: UUID | str) -> None:
    """Invalidate the owner's entries once the session's transaction commits.

    Before the commit, a reader could cache the old rows under the new generation.
    """
    if not get_settings().cache_enabled:
        return

    def bump() -> None:
        try:
            client().set(_generation_key(owner_id), uuid.uuid4().hex)
        except RedisError as exc:
            # The old entries stay valid until their TTL.
            _record_error(GENERATION, "bump", exc)

    on_commit(session, bump)
