"""`django-mongodb-backend`, with two changes for `instances`' indexes (#29, #30).

The backend cannot build a partial index on `isnull`, and a MongoDB partial filter
could not say IS NOT NULL in a form a `submitted_at != null` query uses anyway. So an
index whose whole condition is "these fields are not null" is built in full here. It
stays partial on Postgres, and the migrations stay the same for both engines.

The backend also builds every unique field's index as partial (`{field: {$gte: ""}}`),
so that nulls do not collide, as in SQL. Such an index cannot answer `field: null`.
`select_related` on a nullable foreign key is a `$lookup` on the target's `id`, and
for every row whose key is null that lookup then scans the whole target collection:
on the load-test data, `Questionnaire` -> `Battery` read 2.8 million documents to
return 10 rows (#30). A field that can never be null loses nothing with a full
unique index, so it gets one here. Migration 0004 rebuilds indexes made before this.
"""

from django.db.models import Field, Index, Q
from django_mongodb_backend.base import DatabaseWrapper as MongoDatabaseWrapper
from django_mongodb_backend.schema import DatabaseSchemaEditor as MongoSchemaEditor
from pymongo import ASCENDING, IndexModel


def _only_not_null(condition: Q) -> bool:
    return (
        condition.connector == Q.AND
        and not condition.negated
        and all(
            isinstance(child, tuple)
            and child[0].endswith("__isnull")
            and child[1] is False
            for child in condition.children
        )
    )


class DatabaseSchemaEditor(MongoSchemaEditor):
    def add_index(self, model, index, **kwargs):
        if index.condition is not None and _only_not_null(index.condition):
            index = Index(fields=index.fields, name=index.name)
        super().add_index(model, index, **kwargs)

    def _add_field_unique(self, model, field: Field, column_prefix: str = "") -> None:
        if field.null:
            super()._add_field_unique(model, field, column_prefix=column_prefix)
            return
        column = column_prefix + field.column
        name = str(self._unique_constraint_name(model._meta.db_table, [column]))
        self.get_collection(model._meta.db_table).create_indexes(
            [IndexModel([(column, ASCENDING)], name=name, unique=True)]
        )


class DatabaseWrapper(MongoDatabaseWrapper):
    SchemaEditorClass = DatabaseSchemaEditor
