import os

from .e2e import *

# The parity suite (backend/parity/, #34) starts this service next to its own stub
# `instances`, on ports and a database it picks per run.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ["PARITY_DATABASE"],
    }
}
INSTANCES_INTERNAL_URL = os.environ["PARITY_INSTANCES_URL"]
# Revoke broadcasts to workers. In memory, so the suite needs no Redis.
CELERY_BROKER_URL = "memory://"
