from common.settings.dev import *

from .service import *

# After the import: each profile picks its own backend.
CACHES = cache_with_prefix(CACHES, "instances")

DATABASES = {
    "default": env.db(
        "INSTANCES_DATABASE_URL",
        default="postgres://appuser:apppassword@localhost:5437/instancesdb",
    ),
}
SIMPLE_JWT = jwt_settings(can_sign=False, dev_fallback=True)
PEER_OUTBOUND_TOKEN = INSTANCES_TO_CATALOG_TOKEN
PEER_INBOUND_TOKEN = CATALOG_TO_INSTANCES_TOKEN
