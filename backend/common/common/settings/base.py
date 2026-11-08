from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

from common.dev_keys import DEV_SIGNING_KEY, DEV_VERIFYING_KEY

env = environ.Env()

# One .env at the repo root, shared with the frontend. Containers get vars via env_file.
# Located from here (backend/common/common/settings/), and absent inside images.
_env_file = Path(__file__).resolve().parents[4] / ".env"
if _env_file.is_file():
    environ.Env.read_env(_env_file)

SECRET_KEY = env("SECRET_KEY")

BASE_INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "django_prometheus",
]

MIDDLEWARE = [
    # First: answers /metrics before the HTTPS redirect and host validation,
    # since Prometheus scrapes by IP. See common/metrics.py.
    "common.metrics.MetricsEndpointMiddleware",
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
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"  # noqa: E501
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

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Cache ──────────────────────────────────────────────────────────────────────
# Reads go through common/cache.py, which falls back to the database when Redis
# fails. The timeouts bound how long a failing Redis can hold up a request. db 1:
# on the dev stack this Redis is also the Celery broker (db 0).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("CACHE_REDIS_URL", default="redis://localhost:6380/1"),
        "OPTIONS": {"socket_connect_timeout": 0.1, "socket_timeout": 0.1},
    }
}
# False bypasses the cache without a code change (cache-off load-test runs, #11).
CACHE_ENABLED = env.bool("CACHE_ENABLED", default=True)

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
    "DEFAULT_PAGINATION_CLASS": "common.pagination.StandardPagination",
}


def jwt_settings(*, can_sign: bool, dev_fallback: bool, use_env: bool = True) -> dict:
    """RS256, so a service without the private key can verify but never mint (#13).

    `use_env=False` ignores JWT_* in the environment and gives the dev pair: tests sign
    with DEV_SIGNING_KEY, so a key in a developer's `.env` must not reach them (#33).
    """
    signing = verifying = ""
    if use_env:
        if can_sign:
            signing = env.str("JWT_SIGNING_KEY", default="", multiline=True)
        verifying = env.str("JWT_VERIFYING_KEY", default="", multiline=True)
    if dev_fallback:
        signing = (signing or DEV_SIGNING_KEY) if can_sign else ""
        verifying = verifying or DEV_VERIFYING_KEY
    else:
        if not verifying or (can_sign and not signing):
            raise ImproperlyConfigured("Set JWT_SIGNING_KEY and JWT_VERIFYING_KEY.")
        if signing.strip() == DEV_SIGNING_KEY.strip():
            raise ImproperlyConfigured("JWT_SIGNING_KEY is the published dev key.")
    return {
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
        "ROTATE_REFRESH_TOKENS": True,
        "BLACKLIST_AFTER_ROTATION": False,
        "AUTH_HEADER_TYPES": ("Bearer",),
        "ALGORITHM": "RS256",
        "SIGNING_KEY": signing,
        "VERIFYING_KEY": verifying,
    }


def cache_with_prefix(caches: dict, prefix: str) -> dict:
    """A service's own keys, so one service's generation never touches the other's."""
    return {"default": {**caches["default"], "KEY_PREFIX": prefix}}


def prod_database(url_var: str) -> dict:
    return {
        **env.db(url_var),
        # Keep each worker's connection for this many seconds instead of opening
        # (TCP + auth handshake) one per request. 0 = per request. #9, Phase 6.
        "CONN_MAX_AGE": env.int("CONN_MAX_AGE", default=60),
        # Check a reused connection before each request, so a dropped one is
        # replaced instead of failing that request.
        "CONN_HEALTH_CHECKS": True,
    }


def require_peer_tokens(*tokens: str) -> None:
    if not all(tokens):
        raise ImproperlyConfigured(
            "Set CATALOG_TO_INSTANCES_TOKEN and INSTANCES_TO_CATALOG_TOKEN."
        )


# Calls between the services (#13). Short, so a dead peer never holds a request long.
PEER_CONNECT_TIMEOUT = env.float("PEER_CONNECT_TIMEOUT", default=0.5)
PEER_READ_TIMEOUT = env.float("PEER_READ_TIMEOUT", default=2.0)
CATALOG_TO_INSTANCES_TOKEN = env("CATALOG_TO_INSTANCES_TOKEN", default="")
INSTANCES_TO_CATALOG_TOKEN = env("INSTANCES_TO_CATALOG_TOKEN", default="")
CATALOG_INTERNAL_URL = env("CATALOG_INTERNAL_URL", default="http://localhost:8006")
INSTANCES_INTERNAL_URL = env("INSTANCES_INTERNAL_URL", default="http://localhost:8007")
