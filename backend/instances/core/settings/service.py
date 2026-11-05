"""What only `instances` has. Everything shared is in common/settings/."""

from pathlib import Path

from common.settings.base import BASE_INSTALLED_APPS, REST_FRAMEWORK

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [*BASE_INSTALLED_APPS, "apps.questionnaires"]
ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"
STATIC_URL = "/instances-static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# This service's admin shares an origin with catalog's, behind the gateway.
SESSION_COOKIE_NAME = "instances_sessionid"
CSRF_COOKIE_NAME = "instances_csrftoken"

# Labels on app_cache_requests_total, so a fixed list. See common/cache.py.
CACHE_GROUPS = frozenset({"dashboard", "dashboard-scores", "pdf"})

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.questionnaires.auth.OwnerJWTAuthentication",
    ],
}

CATALOG_CLIENT = "apps.questionnaires.catalog_client.HttpCatalog"
