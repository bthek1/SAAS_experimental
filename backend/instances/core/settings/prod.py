from common.settings.prod import *

from .database import engine_settings, instances_database
from .service import *

# After the import: each profile picks its own backend.
CACHES = cache_with_prefix(CACHES, "instances")

DATABASES = {"default": instances_database(production=True)}
INSTALLED_APPS, DEFAULT_AUTO_FIELD, MIGRATION_MODULES = engine_settings(
    DATABASES["default"], INSTALLED_APPS, DEFAULT_AUTO_FIELD
)
SIMPLE_JWT = jwt_settings(can_sign=False, dev_fallback=False)
PEER_OUTBOUND_TOKEN = INSTANCES_TO_CATALOG_TOKEN
PEER_INBOUND_TOKEN = CATALOG_TO_INSTANCES_TOKEN
