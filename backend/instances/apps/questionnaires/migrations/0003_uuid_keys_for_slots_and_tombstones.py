"""UUID primary keys for BatteryTypeRefSlot and RetiredRef (#29).

MongoDB's backend refuses integer auto keys, and AGENTS.md asks for UUIDs anyway.
Written rather than generated: Django's own AlterField would cast integer to uuid,
which Postgres cannot do with rows present. On Postgres each id becomes a uuid made
from its hex value, in place, so tombstones and slots survive. Elsewhere (SQLite,
a fresh MongoDB) the tables are empty here, and the ordinary schema change is used.
"""

import uuid

from django.db import migrations, models

TABLES = {
    "batterytyperefslot": "questionnaires_batterytyperefslot",
    "retiredref": "questionnaires_retiredref",
}


def uuid_keys(apps, schema_editor):
    for model_name, table in TABLES.items():
        if schema_editor.connection.vendor == "postgresql":
            quoted = schema_editor.quote_name(table)
            schema_editor.execute(
                f"ALTER TABLE {quoted} ALTER COLUMN id DROP IDENTITY IF EXISTS"
            )
            schema_editor.execute(f"ALTER TABLE {quoted} ALTER COLUMN id DROP DEFAULT")
            schema_editor.execute(
                f"ALTER TABLE {quoted} ALTER COLUMN id TYPE uuid "
                "USING lpad(to_hex(id), 32, '0')::uuid"
            )
            continue
        model = apps.get_model("questionnaires", model_name)
        old = model._meta.get_field("id")
        new = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
        new.set_attributes_from_name("id")
        new.model = model
        schema_editor.alter_field(model, old, new)


ID = models.UUIDField(
    default=uuid.uuid4, editable=False, primary_key=True, serialize=False
)


class Migration(migrations.Migration):
    dependencies = [
        ("questionnaires", "0002_order_ties_by_id"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Irreversible: the old integers are not kept.
                migrations.RunPython(uuid_keys),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="batterytyperefslot", name="id", field=ID
                ),
                migrations.AlterField(model_name="retiredref", name="id", field=ID),
            ],
        ),
    ]
