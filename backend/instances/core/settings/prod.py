from common.settings.prod import *

from .service import *

# After the import: each profile picks its own backend.
CACHES = cache_with_prefix(CACHES, "instances")

DATABASES = {"default": prod_database("INSTANCES_DATABASE_URL")}
SIMPLE_JWT = jwt_settings(can_sign=False, dev_fallback=False)
PEER_OUTBOUND_TOKEN = INSTANCES_TO_CATALOG_TOKEN
PEER_INBOUND_TOKEN = CATALOG_TO_INSTANCES_TOKEN
