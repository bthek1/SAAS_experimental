from datetime import timedelta
from pathlib import Path

import environ

env = environ.Env()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# One .env at the repo root, shared with the frontend. Containers get vars via env_file.
environ.Env.read_env(BASE_DIR.parent / ".env")

SECRET_KEY = env("SECRET_KEY")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_celery_results",
    "django_celery_beat",
    "django_prometheus",
    # Local
    "apps.accounts",
    "apps.utils",
    "apps.catalog",
    "apps.questionnaires",
]

MIDDLEWARE = [
    # First: answers /metrics before the HTTPS redirect and host validation,
    # since Prometheus scrapes by IP. See apps/utils/metrics.py.
    "apps.utils.metrics.MetricsEndpointMiddleware",
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

# Peers allowed to scrape /metrics (Prometheus). Anyone else gets a 404.
METRICS_ALLOWED_CIDRS = env.list(
    "METRICS_ALLOWED_CIDRS", default=["127.0.0.1/32", "::1/128"]
)

# gunicorn's on_starting hook empties this directory (gunicorn.conf.py), but
# management commands such as migrate run before gunicorn and write metrics
# there too, which fails if it does not exist yet.
if _multiproc_dir := env("PROMETHEUS_MULTIPROC_DIR", default=""):
    Path(_multiproc_dir).mkdir(parents=True, exist_ok=True)

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

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

# ── Cache ──────────────────────────────────────────────────────────────────────
# Reads go through apps/utils/cache.py, which falls back to the database when Redis
# fails. The timeouts bound how long a failing Redis can hold up a request. db 1:
# on the dev stack this Redis is also the Celery broker (db 0).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("CACHE_REDIS_URL", default="redis://localhost:6380/1"),
        "KEY_PREFIX": "saas",
        "OPTIONS": {"socket_connect_timeout": 0.1, "socket_timeout": 0.1},
    }
}
# False bypasses the cache without a code change (cache-off load-test runs, #11).
CACHE_ENABLED = env.bool("CACHE_ENABLED", default=True)

AUTH_USER_MODEL = "accounts.CustomUser"

# Let the SPA (a different origin) read the filename of file downloads such as
# the questionnaire PDF. Allowed origins are set per environment.
CORS_EXPOSE_HEADERS = ["Content-Disposition"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    # Every list endpoint is paginated: {count, next, previous, results} (#10).
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}
