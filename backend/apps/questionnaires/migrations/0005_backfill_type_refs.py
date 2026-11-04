"""Copy every existing type to its ref, with the same id (#13)."""

from django.db import migrations

BATCH = 500


def backfill(apps, schema_editor):
    qtype = apps.get_model("catalog", "QuestionnaireType")
    btype = apps.get_model("catalog", "BatteryType")
    item = apps.get_model("catalog", "BatteryTypeItem")
    qref = apps.get_model("questionnaires", "QuestionnaireTypeRef")
    bref = apps.get_model("questionnaires", "BatteryTypeRef")
    slot = apps.get_model("questionnaires", "BatteryTypeRefSlot")

    qref.objects.bulk_create(
        (
            qref(
                id=row.id,
                owner_id=row.owner_id,
                title=row.title,
                questionnaire_json=row.questionnaire_json,
                created_at=row.created_at,
                updated_at=row.updated_at,
                version=row.version,
            )
            for row in qtype.objects.iterator(chunk_size=BATCH)
        ),
        batch_size=BATCH,
    )
    bref.objects.bulk_create(
        (
            bref(
                id=row.id,
                owner_id=row.owner_id,
                title=row.title,
                description=row.description,
                created_at=row.created_at,
                updated_at=row.updated_at,
                version=row.version,
            )
            for row in btype.objects.iterator(chunk_size=BATCH)
        ),
        batch_size=BATCH,
    )
    slot.objects.bulk_create(
        (
            slot(
                battery_type_id=row.battery_type_id,
                questionnaire_type_id=row.questionnaire_type_id,
                order=row.order,
            )
            for row in item.objects.iterator(chunk_size=BATCH)
        ),
        batch_size=BATCH,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0002_version_and_outbox"),
        ("questionnaires", "0004_type_refs"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
