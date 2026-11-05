"""`adopt_monolith_db` brings a pre-split database up to the baseline in place (#13).

These change the schema, so they need real commits and put back what they remove.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from .factories import QuestionnaireTypeFactory
from .management.commands.adopt_monolith_db import BASELINE
from .models import BatteryType, OutboxEvent, QuestionnaireType


def columns(model) -> set[str]:
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(
            cursor, model._meta.db_table
        )
    return {column.name for column in description}


@pytest.fixture
def pre_split_database(transactional_db):  # noqa: ARG001
    """As `main` left it: no version columns, no outbox, no baseline recorded."""
    with connection.schema_editor() as editor:
        for model in (QuestionnaireType, BatteryType):
            editor.remove_field(model, model._meta.get_field("version"))
        editor.delete_model(OutboxEvent)
    recorder = MigrationRecorder(connection)
    recorder.record_unapplied(*BASELINE)
    yield
    # Whatever the test did, leave the schema the other tests expect.
    call_command("adopt_monolith_db", verbosity=0)
    recorder.record_applied(*BASELINE)


def adopt(capsys) -> str:
    call_command("adopt_monolith_db")
    return capsys.readouterr().out


def test_baseline_name_is_the_real_migration(db):  # noqa: ARG001
    """Renaming the migration would make `migrate` try to create existing tables."""
    assert BASELINE in MigrationRecorder(connection).applied_migrations()


@pytest.mark.usefixtures("pre_split_database")
def test_adds_what_the_split_needs_and_records_the_baseline(capsys):
    assert "version" not in columns(QuestionnaireType)

    assert "adopted" in adopt(capsys)

    assert "version" in columns(QuestionnaireType)
    assert "version" in columns(BatteryType)
    assert OutboxEvent._meta.db_table in connection.introspection.table_names()
    assert BASELINE in MigrationRecorder(connection).applied_migrations()


@pytest.mark.usefixtures("pre_split_database")
def test_running_it_again_changes_nothing(capsys):
    adopt(capsys)
    assert "already recorded" in adopt(capsys)
    assert OutboxEvent.objects.count() == 0


@pytest.mark.usefixtures("transactional_db")
def test_keeps_existing_rows(capsys):
    qtype = QuestionnaireTypeFactory(title="From the monolith")
    with connection.schema_editor() as editor:
        editor.remove_field(
            QuestionnaireType, QuestionnaireType._meta.get_field("version")
        )

    adopt(capsys)

    assert QuestionnaireType.objects.get(pk=qtype.pk).title == "From the monolith"


def test_does_nothing_on_a_fresh_database(capsys, mocker, db):  # noqa: ARG001
    mocker.patch.object(connection.introspection, "table_names", return_value=[])
    assert "nothing to adopt" in adopt(capsys)
