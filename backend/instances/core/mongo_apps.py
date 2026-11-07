"""Django's own apps, with ObjectId primary keys, for when `instances` runs on MongoDB.

Selected by `core/settings/database.py` (#29). Their migrations are generated into
`mongo_migrations/`, since Django's ship with integer ids.
"""

from django.contrib.admin.apps import AdminConfig
from django.contrib.auth.apps import AuthConfig
from django.contrib.contenttypes.apps import ContentTypesConfig

OBJECT_ID = "django_mongodb_backend.fields.ObjectIdAutoField"


class MongoAdminConfig(AdminConfig):
    default_auto_field = OBJECT_ID


class MongoAuthConfig(AuthConfig):
    default_auto_field = OBJECT_ID


class MongoContentTypesConfig(ContentTypesConfig):
    default_auto_field = OBJECT_ID
