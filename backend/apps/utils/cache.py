"""Server-side cache for expensive reads (#11).

Every cached read goes through `cached()`:

- `owner_id` is required, so a key cannot be built without a tenant.
- A Redis failure is logged and counted, then the value is computed as if there
  were no cache. A cache problem never fails a request.
- `params` must come from validated data, never a raw query string.

Each owner has a generation, part of every key. `bump_owner_generation()` replaces
it, which makes all of that owner's entries unreachable without scanning keys. The
generation is read before computing, so a write that lands during `compute()` leaves
that result under the old generation. It is a random value rather than a counter: a
counter restarting after eviction would bring old entries back.
"""

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from prometheus_client import Counter
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# Labels on the metric below, so a fixed list. Never label by owner, URL or id.
GROUPS = frozenset({"dashboard", "dashboard-scores", "pdf", "type-list"})
GENERATION = "generation"

CACHE_REQUESTS = Counter(
    "app_cache_requests_total",
    "Cached reads by group and result (hit, miss, error).",
    ["group", "result"],
)

_MISS = object()


def _generation_key(owner_id: UUID | str) -> str:
    return f"generation:{owner_id}"


def _new_generation() -> str:
    return uuid.uuid4().hex


def _entry_key(
    group: str, owner_id: UUID | str, generation: Any, params: dict, version: int
) -> str:
    encoded = json.dumps(params, sort_keys=True, default=str).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{group}:v{version}:{owner_id}:{generation}:{digest}"


def _record_error(group: str, operation: str, exc: RedisError) -> None:
    CACHE_REQUESTS.labels(group=group, result="error").inc()
    logger.warning("cache %s failed for %s: %s", operation, group, exc)


def cached[T](
    group: str,
    *,
    owner_id: UUID | str,
    params: dict,
    ttl: int,
    compute: Callable[[], T],
    version: int = 1,
    use_generation: bool = True,
    store_if: Callable[[T], bool] | None = None,
) -> T:
    """Return the cached value for this owner and params, or compute and store it.

    Bump `version` when the shape of the value changes. An exception from `compute`
    propagates and stores nothing. Pass `use_generation=False` only when `params`
    alone identify the content, so nothing needs invalidating. `store_if` can refuse
    a value, such as one too large to hold.
    """
    if group not in GROUPS:
        raise ValueError(f"unknown cache group {group!r}: add it to GROUPS")
    if not settings.CACHE_ENABLED:
        return compute()

    try:
        generation = (
            cache.get_or_set(_generation_key(owner_id), _new_generation, timeout=None)
            if use_generation
            else None
        )
        key = _entry_key(group, owner_id, generation, params, version)
        value: Any = cache.get(key, _MISS)
    except RedisError as exc:
        _record_error(group, "read", exc)
        return compute()

    if value is not _MISS:
        CACHE_REQUESTS.labels(group=group, result="hit").inc()
        return value

    CACHE_REQUESTS.labels(group=group, result="miss").inc()
    value = compute()
    if store_if is not None and not store_if(value):
        return value
    try:
        cache.set(key, value, timeout=ttl)
    except RedisError as exc:
        _record_error(group, "write", exc)
    return value


def bump_owner_generation(owner_id: UUID | str) -> None:
    """Invalidate the owner's entries once the current transaction commits.

    Before the commit, a reader could cache the old rows under the new generation.
    """
    if not settings.CACHE_ENABLED:
        return

    def bump() -> None:
        try:
            cache.set(_generation_key(owner_id), _new_generation(), timeout=None)
        except RedisError as exc:
            # The old entries stay valid until their TTL.
            _record_error(GENERATION, "bump", exc)

    transaction.on_commit(bump)
