from common.settings.dev import *

from .service import *

# After the import: each profile picks its own backend.
CACHES = cache_with_prefix(CACHES, "catalog")

DATABASES = {
    "default": env.db(
        "DATABASE_URL", default="postgres://appuser:apppassword@localhost:5435/appdb"
    ),
}
SIMPLE_JWT = jwt_settings(can_sign=True, dev_fallback=True)
PEER_OUTBOUND_TOKEN = CATALOG_TO_INSTANCES_TOKEN
PEER_INBOUND_TOKEN = INSTANCES_TO_CATALOG_TOKEN
