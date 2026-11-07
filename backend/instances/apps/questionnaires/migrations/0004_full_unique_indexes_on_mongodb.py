"""Full unique indexes for fields that are never null, on MongoDB (#30).

`core/mongodb/base.py` now builds them in full, so a `$lookup` on a null foreign key
uses the index instead of scanning the target collection. This rebuilds the partial
ones a database made before that change still has. Nothing to do on other engines.
"""

from django.db import migrations


def full_unique_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "mongodb":
        return
    for model in apps.get_app_config("questionnaires").get_models():
        collection = schema_editor.get_collection(model._meta.db_table)
        existing = collection.index_information()
        for field in model._meta.local_concrete_fields:
            if not field.unique or field.null:
                continue
            name = str(
                schema_editor._unique_constraint_name(
                    model._meta.db_table, [field.column]
                )
            )
            if "partialFilterExpression" not in existing.get(name, {}):
                continue
            collection.drop_index(name)
            schema_editor._add_field_unique(model, field)


class Migration(migrations.Migration):
    dependencies = [
        ("questionnaires", "0003_uuid_keys_for_slots_and_tombstones"),
    ]

    operations = [
        migrations.RunPython(full_unique_indexes, migrations.RunPython.noop),
    ]
