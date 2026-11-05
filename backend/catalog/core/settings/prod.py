from common.settings.prod import *

from .service import *

# After the import: each profile picks its own backend.
CACHES = cache_with_prefix(CACHES, "catalog")

DATABASES = {"default": prod_database("DATABASE_URL")}
SIMPLE_JWT = jwt_settings(can_sign=True, dev_fallback=False)
PEER_OUTBOUND_TOKEN = CATALOG_TO_INSTANCES_TOKEN
PEER_INBOUND_TOKEN = INSTANCES_TO_CATALOG_TOKEN
