from .base import *
from .dev_keys import DEV_SIGNING_KEY, DEV_VERIFYING_KEY

DEBUG = False

SIMPLE_JWT = {
    **SIMPLE_JWT,
    "SIGNING_KEY": DEV_SIGNING_KEY,
    "VERIFYING_KEY": DEV_VERIFYING_KEY,
}
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_FROM_EMAIL = "root@localhost"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# No Redis, and off by default so tests (and e2e, which inherits this) see fresh
# data. Cache tests opt in with the `cache_on` fixture.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CACHE_ENABLED = False

# Run Celery tasks synchronously in tests — no broker required.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
