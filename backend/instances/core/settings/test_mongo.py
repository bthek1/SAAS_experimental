"""`test`, on MongoDB instead of SQLite (#29). Same tests, so both engines behave alike.

    cd backend && uv run pytest instances --ds core.settings.test_mongo

`INSTANCES_TEST_MONGO_URL` defaults to the dev stack's `instances_mongo`. Django
creates and drops its own `test_instances` database there, so dev data is untouched.
"""

from .database import engine_settings, mongo_database
from .test import *

DATABASES = {
    "default": mongo_database(
        env.str(
            "INSTANCES_TEST_MONGO_URL",
            default="mongodb://127.0.0.1:27018/instances?replicaSet=rs0&directConnection=true",
        )
    )
}
INSTALLED_APPS, DEFAULT_AUTO_FIELD, MIGRATION_MODULES = engine_settings(
    DATABASES["default"], INSTALLED_APPS, DEFAULT_AUTO_FIELD
)
