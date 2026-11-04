"""Hand the type models to `catalog`. State only, no schema SQL (#13)."""

import django.db.models.deletion
from django.db import migrations, models

MOVED = ["questionnairetype", "batterytype", "batterytypeitem"]


def relabel_content_types(apps, from_label, to_label):
    # Keeps granted permissions and admin history pointing at the moved models.
    content_type = apps.get_model("contenttypes", "ContentType")
    for model in MOVED:
        moving = content_type.objects.filter(app_label=from_label, model=model)
        if moving.exists():
            # A separate `migrate catalog` has already created an empty target.
            content_type.objects.filter(app_label=to_label, model=model).delete()
            moving.update(app_label=to_label)


def forwards(apps, schema_editor):
    relabel_content_types(apps, "questionnaires", "catalog")


def backwards(apps, schema_editor):
    relabel_content_types(apps, "catalog", "questionnaires")


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("catalog", "0001_initial"),
        ("questionnaires", "0002_dashboard_submitted_indexes"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="questionnaire",
                    name="questionnaire_type",
                    field=models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name="instances", to="catalog.questionnairetype"),
                ),
                migrations.AlterField(
                    model_name="battery",
                    name="battery_type",
                    field=models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name="instances", to="catalog.batterytype"),
                ),
                migrations.RemoveField(model_name="batterytype", name="questionnaire_types"),
                migrations.DeleteModel(name="BatteryTypeItem"),
                migrations.DeleteModel(name="BatteryType"),
                migrations.DeleteModel(name="QuestionnaireType"),
            ],
        ),
        migrations.RunPython(forwards, backwards),
    ]
