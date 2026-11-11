"""Alembic for `catalogdb` (#35).

Revision 0001 is the schema Django's migrations left. A database Django built is
stamped at 0001, not migrated. Only this service's tables are compared: Django's
own (`auth_*`, `django_*`, the user's group links) and Celery's results are not
ours to change.
"""

from logging.config import fileConfig

from alembic import context

from catalog_fastapi.db import get_engine
from catalog_fastapi.models import Base

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

OURS = set(Base.metadata.tables)


def include_name(name, type_, parent_names) -> bool:  # noqa: ARG001
    return type_ != "table" or name in OURS


def run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        include_name=include_name,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# Tests pass a connection in; everyone else gets one from the settings.
if (given := context.config.attributes.get("connection")) is not None:
    run(given)
else:
    with get_engine().connect() as connection:
        run(connection)
