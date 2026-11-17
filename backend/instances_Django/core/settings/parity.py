from .test import *

# backend/parity_instances with INSTANCES_IMPL=django (#51): the test profile (dev
# JWT pair, test peer tokens, cache off), on the suite's throwaway Postgres, reaching
# its stub catalog over real HTTP. DJANGO_SETTINGS_MODULE=core.settings.parity.
DATABASES = {"default": env.db("INSTANCES_DATABASE_URL")}
CATALOG_INTERNAL_URL = env("CATALOG_INTERNAL_URL")
CATALOG_CLIENT = "apps.questionnaires.catalog_client.HttpCatalog"
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
