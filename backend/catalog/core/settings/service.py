"""What only `catalog` has. Everything shared is in common/settings/."""

from pathlib import Path

from common.settings.base import BASE_INSTALLED_APPS, TIME_ZONE, env

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    *BASE_INSTALLED_APPS,
    "rest_framework_simplejwt",
    "django_celery_results",
    "django_celery_beat",
    "apps.accounts",
    "apps.utils",
    "apps.catalog",
]
ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"
STATIC_ROOT = BASE_DIR / "staticfiles"
AUTH_USER_MODEL = "accounts.CustomUser"

# Labels on app_cache_requests_total, so a fixed list. See common/cache.py.
CACHE_GROUPS = frozenset({"type-list"})

INSTANCES_CLIENT = "apps.catalog.instances_client.HttpInstances"

# ── Celery ─────────────────────────────────────────────────────────────────────
# docker-compose publishes Redis on host port 6380 (6380:6379) to avoid
# clashing with a locally installed Redis. Inside Compose, use redis://redis:6379/0.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6380/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_RESULT_EXTENDED = True  # stores args, kwargs, worker, runtime
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Reliability & observability
CELERY_TASK_TRACK_STARTED = True  # exposes STARTED state
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_ACKS_LATE = True  # task survives worker crash
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # prevents long tasks blocking short ones
CELERY_TASK_SOFT_TIME_LIMIT = 300  # raises SoftTimeLimitExceeded at 5 min
CELERY_TASK_TIME_LIMIT = 360  # hard kill at 6 min
