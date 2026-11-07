"""Which database `instances` runs on: Postgres or MongoDB, by URL scheme (#29).

`INSTANCES_DATABASE_URL=postgres://...` behaves exactly as before. A `mongodb://` URL
(a replica set, since `apps/questionnaires/db.py` needs transactions, with the database
name in its path) selects `django-mongodb-backend`. That also swaps in ObjectId versions
of Django's own apps and their migrations. Use both together:

    DATABASES = {"default": instances_database(...)}
    INSTALLED_APPS, DEFAULT_AUTO_FIELD, MIGRATION_MODULES = engine_settings(
        DATABASES["default"], INSTALLED_APPS, DEFAULT_AUTO_FIELD
    )
"""

from common.settings.base import env

MONGO_SCHEMES = ("mongodb://", "mongodb+srv://")
MONGO_ENGINE = "core.mongodb"  # django_mongodb_backend, see core/mongodb/base.py

_MONGO_APPS = {
    "django.contrib.admin": "core.mongo_apps.MongoAdminConfig",
    "django.contrib.auth": "core.mongo_apps.MongoAuthConfig",
    "django.contrib.contenttypes": "core.mongo_apps.MongoContentTypesConfig",
}
_MONGO_MIGRATIONS = {
    "admin": "mongo_migrations.admin",
    "auth": "mongo_migrations.auth",
    "contenttypes": "mongo_migrations.contenttypes",
}


def mongo_database(url: str) -> dict:
    # An empty NAME makes the backend read it from the URL's path.
    return {"ENGINE": MONGO_ENGINE, "HOST": url, "NAME": ""}


def instances_database(*, default: str | None = None, production: bool = False) -> dict:
    url = env.str("INSTANCES_DATABASE_URL", default=default)
    if url.startswith(MONGO_SCHEMES):
        # pymongo pools connections itself, so CONN_MAX_AGE and health checks,
        # which manage Django's per-thread connection, do not apply.
        return mongo_database(url)
    database = env.db_url_config(url)
    if production:
        # As prod_database() in common/settings/base.py.
        database["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
        database["CONN_HEALTH_CHECKS"] = True
    return database


def engine_settings(
    database: dict, installed_apps: list[str], default_auto_field: str
) -> tuple[list[str], str, dict[str, str]]:
    if database["ENGINE"] != MONGO_ENGINE:
        return installed_apps, default_auto_field, {}
    apps = [_MONGO_APPS.get(app, app) for app in installed_apps]
    return (
        ["django_mongodb_backend", *apps],
        "django_mongodb_backend.fields.ObjectIdAutoField",
        _MONGO_MIGRATIONS,
    )
