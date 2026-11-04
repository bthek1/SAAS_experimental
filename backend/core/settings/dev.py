from .base import *
from .dev_keys import DEV_SIGNING_KEY, DEV_VERIFYING_KEY

DEBUG = True

# A new dict: core/settings/__init__.py imports this module before any other, so
# changing base's in place would hand the dev key to prod.
SIMPLE_JWT = {
    **SIMPLE_JWT,
    "SIGNING_KEY": SIMPLE_JWT["SIGNING_KEY"] or DEV_SIGNING_KEY,
    "VERIFYING_KEY": SIMPLE_JWT["VERIFYING_KEY"] or DEV_VERIFYING_KEY,
}
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

DATABASES = {
    "default": env.db(
        "DATABASE_URL", default="postgres://appuser:apppassword@localhost:5432/appdb"
    ),
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@example.com")

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:5174"]
)

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^http://192\.168\.\d+\.\d+:\d+$",
]
