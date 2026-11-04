from django.core.exceptions import ImproperlyConfigured

from .base import *
from .dev_keys import DEV_SIGNING_KEY

DEBUG = False

SECRET_KEY = env("SECRET_KEY")

if not SIMPLE_JWT["SIGNING_KEY"] or not SIMPLE_JWT["VERIFYING_KEY"]:
    raise ImproperlyConfigured("Set JWT_SIGNING_KEY and JWT_VERIFYING_KEY.")
if SIMPLE_JWT["SIGNING_KEY"].strip() == DEV_SIGNING_KEY.strip():
    raise ImproperlyConfigured("JWT_SIGNING_KEY is the published dev key.")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

DATABASES = {
    "default": {
        **env.db("DATABASE_URL"),
        # Keep each worker's connection for this many seconds instead of opening
        # (TCP + auth handshake) one per request. 0 = per request. #9, Phase 6.
        "CONN_MAX_AGE": env.int("CONN_MAX_AGE", default=60),
        # Check a reused connection before each request, so a dropped one is
        # replaced instead of failing that request.
        "CONN_HEALTH_CHECKS": True,
    },
}

# No default here: the cache fails open, so a wrong URL would otherwise run
# uncached with no other symptom.
CACHES["default"]["LOCATION"] = env("CACHE_REDIS_URL")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@example.com")

# HTTPS / security hardening
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
