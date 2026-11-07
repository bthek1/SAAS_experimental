"""Choosing Postgres or MongoDB from INSTANCES_DATABASE_URL (#29)."""

import uuid

import pytest
from core.settings.database import (
    MONGO_ENGINE,
    engine_settings,
    instances_database,
)
from django.db import connection

from apps.questionnaires.db import is_mongodb
from apps.questionnaires.factories import BatteryTypeFactory, QuestionnaireFactory
from apps.questionnaires.models import Battery, Questionnaire

APPS = ["django.contrib.admin", "django.contrib.auth", "apps.questionnaires"]
BIG = "django.db.models.BigAutoField"


def test_postgres_url_is_unchanged(monkeypatch):
    monkeypatch.setenv("INSTANCES_DATABASE_URL", "postgres://u:p@h:5432/instancesdb")
    database = instances_database(production=True)
    assert database["ENGINE"] == "django.db.backends.postgresql"
    assert database["NAME"] == "instancesdb"
    assert database["CONN_HEALTH_CHECKS"] is True
    assert engine_settings(database, APPS, BIG) == (APPS, BIG, {})


def test_mongodb_url_selects_the_backend_and_objectid_apps(monkeypatch):
    url = "mongodb://u:p@h:27017/instancesdb?replicaSet=rs0"
    monkeypatch.setenv("INSTANCES_DATABASE_URL", url)
    database = instances_database(production=True)
    # pymongo pools its own connections, so Django's connection settings stay out.
    assert database == {"ENGINE": MONGO_ENGINE, "HOST": url, "NAME": ""}
    apps, auto_field, migrations = engine_settings(database, APPS, BIG)
    assert apps == [
        "django_mongodb_backend",
        "core.mongo_apps.MongoAdminConfig",
        "core.mongo_apps.MongoAuthConfig",
        "apps.questionnaires",
    ]
    assert auto_field.endswith("ObjectIdAutoField")
    assert set(migrations) == {"admin", "auth", "contenttypes"}


def test_default_applies_only_without_the_variable(monkeypatch):
    monkeypatch.delenv("INSTANCES_DATABASE_URL", raising=False)
    database = instances_database(default="postgres://u:p@h:5437/fallback")
    assert database["NAME"] == "fallback"


@pytest.mark.django_db
def test_null_foreign_key_join_uses_the_index_on_mongodb():
    """A `$lookup` on a null `battery_id` must not scan every battery (#30)."""
    if not is_mongodb():
        pytest.skip("MongoDB only")
    owner = uuid.uuid4()
    battery_type = BatteryTypeFactory(owner_id=owner)
    for _ in range(5):
        Battery.objects.create(owner_id=owner, battery_type=battery_type)
    QuestionnaireFactory(questionnaire_type__owner_id=owner, battery=None)
    batteries = Battery._meta.db_table
    for name, info in connection.get_collection(batteries).index_information().items():
        if name.endswith("_uniq"):
            assert "partialFilterExpression" not in info, name
    pipeline = [
        {"$match": {"owner_id": owner.hex}},
        {
            "$lookup": {
                "from": batteries,
                "pipeline": [],
                "as": "b",
                "localField": "battery_id",
                "foreignField": "id",
            }
        },
    ]
    plan = connection.database.command(
        "explain",
        {"aggregate": Questionnaire._meta.db_table, "pipeline": pipeline, "cursor": {}},
        verbosity="executionStats",
    )
    lookup = next(stage for stage in plan["stages"] if "$lookup" in stage)
    assert lookup["collectionScans"] == 0
