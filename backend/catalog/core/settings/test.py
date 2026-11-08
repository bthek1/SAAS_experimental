from common.settings.test import *

from .service import *

# After the import: each profile picks its own backend.
CACHES = cache_with_prefix(CACHES, "catalog")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
SIMPLE_JWT = jwt_settings(can_sign=True, dev_fallback=True, use_env=False)
PEER_OUTBOUND_TOKEN = CATALOG_TO_INSTANCES_TOKEN
PEER_INBOUND_TOKEN = INSTANCES_TO_CATALOG_TOKEN

# Run Celery tasks synchronously in tests — no broker required.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

INSTANCES_CLIENT = "apps.catalog.testing.NullInstances"
