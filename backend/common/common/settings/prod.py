from .base import *

DEBUG = False

SECRET_KEY = env("SECRET_KEY")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

require_peer_tokens(CATALOG_TO_INSTANCES_TOKEN, INSTANCES_TO_CATALOG_TOKEN)

# No default here: the cache fails open, so a wrong URL would otherwise run
# uncached with no other symptom.
CACHES = {"default": {**CACHES["default"], "LOCATION": env("CACHE_REDIS_URL")}}

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@example.com")

# HTTPS / security hardening
SECURE_SSL_REDIRECT = True
# The services call each other directly, over a private network.
SECURE_REDIRECT_EXEMPT = [r"^internal/"]
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
