"""Same ids, same RESTRICT, but on the local copies (#13)."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("questionnaires", "0005_backfill_type_refs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="battery",
            name="battery_type",
            field=models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name="instances", to="questionnaires.batterytyperef"),
        ),
        migrations.AlterField(
            model_name="questionnaire",
            name="questionnaire_type",
            field=models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name="instances", to="questionnaires.questionnairetyperef"),
        ),
    ]
