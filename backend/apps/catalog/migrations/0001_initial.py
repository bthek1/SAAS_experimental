"""State only: the tables already exist, created by questionnaires 0001 (#13)."""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("questionnaires", "0002_dashboard_submitted_indexes"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="QuestionnaireType",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("title", models.CharField(max_length=255)),
                        ("questionnaire_json", models.JSONField(blank=True, default=dict)),
                        ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="questionnaire_types", to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        "db_table": "questionnaires_questionnairetype",
                        "ordering": ["-created_at"],
                        "abstract": False,
                        "indexes": [models.Index(fields=["owner", "-created_at"], name="questionnai_owner_i_be24a4_idx")],
                    },
                ),
                migrations.CreateModel(
                    name="BatteryType",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("title", models.CharField(max_length=255)),
                        ("description", models.TextField(blank=True, default="")),
                        ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="battery_types", to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        "db_table": "questionnaires_batterytype",
                        "ordering": ["-created_at"],
                        "abstract": False,
                        "indexes": [models.Index(fields=["owner", "-created_at"], name="questionnai_owner_i_8141dc_idx")],
                    },
                ),
                migrations.CreateModel(
                    name="BatteryTypeItem",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("order", models.PositiveIntegerField()),
                        ("battery_type", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="catalog.batterytype")),
                        ("questionnaire_type", models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name="battery_items", to="catalog.questionnairetype")),
                    ],
                    options={
                        "db_table": "questionnaires_batterytypeitem",
                        "ordering": ["order"],
                        "unique_together": {("battery_type", "order")},
                    },
                ),
                migrations.AddField(
                    model_name="batterytype",
                    name="questionnaire_types",
                    field=models.ManyToManyField(related_name="battery_types", through="catalog.BatteryTypeItem", to="catalog.questionnairetype"),
                ),
            ],
        ),
    ]
