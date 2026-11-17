# Root conftest.py — shared fixtures can be added here.
import pytest
from django.core.cache import cache


@pytest.fixture
def cache_on(settings):
    """Turn the cache on (core.settings.test leaves it off), starting empty."""
    settings.CACHE_ENABLED = True
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(scope="session")
def celery_config():
    """Override broker/backend with in-memory transports for the test suite.

    This prevents any attempt to connect to a real Redis instance even if
    CELERY_TASK_ALWAYS_EAGER is somehow bypassed.
    """
    return {
        "broker_url": "memory://",
        "result_backend": "cache+memory://",
    }
