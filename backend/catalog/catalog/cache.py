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
from .responses import dumps
from .settings import get_settings

logger = logging.getLogger(__name__)

# Not "catalog": Django's cache stored pickles under that prefix.
PREFIX = "catalog-json"
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


def cached(
    group: str,
    *,
    owner_id: UUID | str,
    params: dict,
    ttl: int,
    compute: Callable[[], Any],
    version: int = 1,
) -> bytes:
    """The JSON body for this owner and params: cached, or computed and stored.

    Returns bytes, so a hit goes out as Redis holds it, never decoded and encoded
    again (#41). `compute` must return JSON-serialisable data. Bump `version` when
    its shape changes. An exception from `compute` propagates and stores nothing.
    """
    if group not in CACHE_GROUPS:
        raise ValueError(f"unknown cache group {group!r}: add it to CACHE_GROUPS")
    if not get_settings().cache_enabled:
        return dumps(compute())

    try:
        key = _entry_key(group, owner_id, _generation(owner_id), params, version)
        raw: Any = client().get(key)
    except RedisError as exc:
        _record_error(group, "read", exc)
        return dumps(compute())

    if raw is not None:
        CACHE_REQUESTS.labels(group=group, result="hit").inc()
        return raw if isinstance(raw, bytes) else str(raw).encode("utf-8")

    CACHE_REQUESTS.labels(group=group, result="miss").inc()
    body = dumps(compute())
    try:
        client().set(key, body, ex=ttl)
    except RedisError as exc:
        _record_error(group, "write", exc)
    return body


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
