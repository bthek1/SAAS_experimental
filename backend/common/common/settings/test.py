from .base import *

DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

CATALOG_TO_INSTANCES_TOKEN = "test-catalog-to-instances"
INSTANCES_TO_CATALOG_TOKEN = "test-instances-to-catalog"

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_FROM_EMAIL = "root@localhost"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# No Redis, and off by default so tests (and e2e, which inherits this) see fresh
# data. Cache tests opt in with the `cache_on` fixture.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CACHE_ENABLED = False
