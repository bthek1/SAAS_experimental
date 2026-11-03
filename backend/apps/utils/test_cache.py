"""The cache helper (#11): tenant isolation, invalidation and failing open."""

import uuid

import pytest
from django.core.cache import cache as django_cache
from prometheus_client import REGISTRY
from redis.exceptions import ConnectionError as RedisConnectionError

from . import cache as cache_module
from .cache import bump_owner_generation, cached

pytestmark = pytest.mark.django_db

OWNER = uuid.uuid4()
OTHER = uuid.uuid4()


class Compute:
    """Returns a new value on every call, and counts the calls."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return {"call": self.calls}


def read(compute, *, owner=OWNER, params=None, group="dashboard", **kwargs):
    return cached(
        group,
        owner_id=owner,
        params=params if params is not None else {"days": 7},
        ttl=30,
        compute=compute,
        **kwargs,
    )


def count(group, result):
    labels = {"group": group, "result": result}
    return REGISTRY.get_sample_value("app_cache_requests_total", labels) or 0


@pytest.fixture
def bump(django_capture_on_commit_callbacks):
    """Bump and commit: pytest-django's transaction would hold the callback back."""

    def run(owner=OWNER):
        with django_capture_on_commit_callbacks(execute=True):
            bump_owner_generation(owner)

    return run


@pytest.fixture
def broken_redis(mocker):
    """Every cache operation fails the way a lost connection does."""
    broken = mocker.patch.object(cache_module, "cache")
    error = RedisConnectionError("connection refused")
    broken.get_or_set.side_effect = error
    broken.get.side_effect = error
    broken.set.side_effect = error
    return broken


@pytest.mark.usefixtures("cache_on")
class TestReads:
    def test_hit_returns_cached_value_without_compute(self):
        compute = Compute()
        assert read(compute) == {"call": 1}
        assert read(compute) == {"call": 1}
        assert compute.calls == 1

    def test_hit_and_miss_are_counted_per_group(self):
        hits, misses = count("pdf", "hit"), count("pdf", "miss")
        compute = Compute()
        read(compute, group="pdf")
        read(compute, group="pdf")
        assert count("pdf", "miss") == misses + 1
        assert count("pdf", "hit") == hits + 1

    def test_owner_is_part_of_the_key(self):
        assert read(Compute(), owner=OWNER) == {"call": 1}
        other = Compute()
        read(other, owner=OTHER)
        assert other.calls == 1

    def test_owner_separates_entries_without_the_generation(self):
        # The per-owner generation also separates them, so check the key on its own.
        same_generation = {
            "group": "pdf",
            "generation": "g",
            "params": {},
            "version": 1,
        }
        assert cache_module._entry_key(owner_id=OWNER, **same_generation) != (
            cache_module._entry_key(owner_id=OTHER, **same_generation)
        )

    def test_params_are_part_of_the_key(self):
        compute = Compute()
        read(compute, params={"days": 7})
        read(compute, params={"days": 30})
        assert compute.calls == 2

    def test_param_order_does_not_change_the_key(self):
        compute = Compute()
        read(compute, params={"days": 7, "type": "a"})
        read(compute, params={"type": "a", "days": 7})
        assert compute.calls == 1

    def test_group_and_version_are_part_of_the_key(self):
        compute = Compute()
        read(compute, group="dashboard")
        read(compute, group="dashboard-scores")
        read(compute, group="dashboard", version=2)
        assert compute.calls == 3

    def test_a_falsy_value_is_a_hit(self):
        calls = []

        def compute():
            calls.append(1)
            return []

        assert read(compute) == []
        assert read(compute) == []
        assert len(calls) == 1

    def test_unknown_group_is_refused(self):
        with pytest.raises(ValueError, match="unknown cache group"):
            read(Compute(), group=f"owner-{OWNER}")

    def test_compute_exception_propagates_and_stores_nothing(self):
        def boom():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            read(boom)
        compute = Compute()
        assert read(compute) == {"call": 1}


def test_disabled_bypasses_cache(settings):
    settings.CACHE_ENABLED = False
    compute = Compute()
    read(compute)
    read(compute)
    assert compute.calls == 2


@pytest.mark.usefixtures("cache_on")
class TestInvalidation:
    def test_bump_makes_old_entry_unreachable(self, bump):
        compute = Compute()
        read(compute)
        bump()
        assert read(compute) == {"call": 2}

    def test_bump_leaves_other_owners_alone(self, bump):
        compute = Compute()
        read(compute, owner=OTHER)
        bump(OWNER)
        assert read(compute, owner=OTHER) == {"call": 1}

    def test_write_during_compute_is_not_served_after_bump(self, bump):
        """A reader that saw the old rows must not make them current again."""

        def stale_read_racing_a_write():
            bump()
            return "old rows"

        assert read(stale_read_racing_a_write) == "old rows"
        assert read(lambda: "new rows") == "new rows"

    def test_evicted_generation_does_not_revive_old_entries(self):
        compute = Compute()
        read(compute)
        django_cache.delete(cache_module._generation_key(OWNER))
        assert read(compute) == {"call": 2}

    def test_bump_waits_for_commit(self, django_capture_on_commit_callbacks):
        compute = Compute()
        read(compute)
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            bump_owner_generation(OWNER)
            assert read(compute) == {"call": 1}
        assert len(callbacks) == 1
        callbacks[0]()
        assert read(compute) == {"call": 2}


@pytest.mark.usefixtures("cache_on")
class TestFailingOpen:
    def test_redis_error_runs_compute_and_counts_error(self, broken_redis):
        errors = count("dashboard", "error")
        compute = Compute()
        assert read(compute) == {"call": 1}
        assert read(compute) == {"call": 2}
        assert count("dashboard", "error") == errors + 2
        broken_redis.get.assert_not_called()

    def test_failed_write_still_returns_the_value(self, mocker):
        errors = count("dashboard", "error")
        mocker.patch.object(
            django_cache, "set", side_effect=RedisConnectionError("gone")
        )
        assert read(Compute()) == {"call": 1}
        assert count("dashboard", "error") == errors + 1

    def test_failed_bump_does_not_raise(self, bump, broken_redis):
        errors = count("generation", "error")
        bump()
        assert broken_redis.set.called
        assert count("generation", "error") == errors + 1


@pytest.mark.usefixtures("cache_on")
class TestWithoutGeneration:
    def test_a_bump_does_not_touch_it(self, bump):
        compute = Compute()
        read(compute, group="pdf", use_generation=False)
        bump()
        read(compute, group="pdf", use_generation=False)
        assert compute.calls == 1

    def test_owner_still_separates_entries(self):
        compute = Compute()
        read(compute, owner=OWNER, group="pdf", use_generation=False)
        read(compute, owner=OTHER, group="pdf", use_generation=False)
        assert compute.calls == 2

    def test_store_if_can_refuse_a_value(self):
        compute = Compute()
        read(compute, store_if=lambda _value: False)
        read(compute, store_if=lambda _value: False)
        assert compute.calls == 2
