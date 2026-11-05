from .base import *

DEBUG = True
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

CATALOG_TO_INSTANCES_TOKEN = CATALOG_TO_INSTANCES_TOKEN or "dev-catalog-to-instances"
INSTANCES_TO_CATALOG_TOKEN = INSTANCES_TO_CATALOG_TOKEN or "dev-instances-to-catalog"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@example.com")

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:5174"]
)

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^http://192\.168\.\d+\.\d+:\d+$",
]
