from common.settings.test import *

from .service import *

# After the import: each profile picks its own backend.
CACHES = cache_with_prefix(CACHES, "instances")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
SIMPLE_JWT = jwt_settings(can_sign=False, dev_fallback=True)
PEER_OUTBOUND_TOKEN = INSTANCES_TO_CATALOG_TOKEN
PEER_INBOUND_TOKEN = CATALOG_TO_INSTANCES_TOKEN

CATALOG_CLIENT = "apps.questionnaires.testing.UnreachableCatalog"
