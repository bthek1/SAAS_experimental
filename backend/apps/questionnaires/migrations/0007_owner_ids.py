"""`owner` foreign keys become plain `owner_id` UUID columns, values untouched (#13).

Only the constraint changes in the database. The column keeps its name and its data.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

MODELS = ["questionnaire", "battery", "questionnairetyperef", "batterytyperef"]


def block_inactive_owners(apps, schema_editor):
    user = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    blocked = apps.get_model("questionnaires", "BlockedOwner")
    blocked.objects.bulk_create(
        blocked(owner_id=pk, blocked=True, version=1)
        for pk in user.objects.filter(is_active=False).values_list("pk", flat=True)
    )


def state_operations():
    indexes = {
        "questionnaire": [
            ("questionnai_owner_i_23d4ff_idx", dict(fields=["owner_id", "-created_at"])),
            ("q_owner_submitted", dict(fields=["owner_id", "-submitted_at"], condition=models.Q(submitted_at__isnull=False))),
            ("q_owner_type_submitted", dict(fields=["owner_id", "questionnaire_type", "-submitted_at"], condition=models.Q(submitted_at__isnull=False))),
        ],
        "battery": [("questionnai_owner_i_29bbb3_idx", dict(fields=["owner_id", "-created_at"]))],
        "questionnairetyperef": [("questionnai_owner_i_91d239_idx", dict(fields=["owner_id", "-created_at"]))],
        "batterytyperef": [("questionnai_owner_i_d35b99_idx", dict(fields=["owner_id", "-created_at"]))],
    }
    operations = []
    for model in MODELS:
        for name, _ in indexes[model]:
            operations.append(migrations.RemoveIndex(model_name=model, name=name))
        operations.append(migrations.RemoveField(model_name=model, name="owner"))
        operations.append(
            migrations.AddField(
                model_name=model,
                name="owner_id",
                field=models.UUIDField(db_index=True),
                preserve_default=False,
            )
        )
        for name, options in indexes[model]:
            operations.append(
                migrations.AddIndex(model_name=model, index=models.Index(name=name, **options))
            )
    return operations


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("questionnaires", "0006_point_instances_at_refs"),
    ]

    operations = [
        migrations.CreateModel(
            name="BlockedOwner",
            fields=[
                ("owner_id", models.UUIDField(primary_key=True, serialize=False)),
                ("blocked", models.BooleanField(default=True)),
                ("deleted", models.BooleanField(default=False)),
                ("version", models.PositiveBigIntegerField()),
            ],
        ),
        migrations.RunPython(block_inactive_owners, migrations.RunPython.noop),
        *[
            migrations.AlterField(
                model_name=model,
                name="owner",
                field=models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.CASCADE, related_name=related, to=settings.AUTH_USER_MODEL),
            )
            for model, related in [
                ("questionnaire", "questionnaires"),
                ("battery", "batteries"),
                ("questionnairetyperef", "questionnaire_type_refs"),
                ("batterytyperef", "battery_type_refs"),
            ]
        ],
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=state_operations(),
        ),
    ]
