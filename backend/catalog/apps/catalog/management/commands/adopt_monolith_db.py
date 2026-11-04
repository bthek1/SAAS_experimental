from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from apps.catalog.models import BatteryType, OutboxEvent, QuestionnaireType

BASELINE = ("catalog", "0001_initial")


class Command(BaseCommand):
    help = (
        "Bring a database from before the split up to catalog's baseline, in place "
        "(#13). Safe to run any number of times, and does nothing on a fresh database. "
        "Instance tables are left alone: see instances' import_from_monolith."
    )

    def handle(self, *args, **options):  # noqa: ARG002
        recorder = MigrationRecorder(connection)
        tables = connection.introspection.table_names()
        if QuestionnaireType._meta.db_table not in tables:
            self.stdout.write("no tables from before the split: nothing to adopt")
            return
        recorder.ensure_schema()
        if BASELINE in recorder.applied_migrations():
            # Applied by name, so an adopted database is recorded just as a new one is,
            # but a database from the interim phases still needs its columns checked.
            self._add_missing(tables)
            self.stdout.write("catalog baseline already recorded")
            return
        self._add_missing(tables)
        recorder.record_applied(*BASELINE)
        self.stdout.write("adopted: catalog baseline recorded")

    def _add_missing(self, tables: list[str]) -> None:
        with connection.schema_editor() as editor, connection.cursor() as cursor:
            for model in (QuestionnaireType, BatteryType):
                columns = {
                    column.name
                    for column in connection.introspection.get_table_description(
                        cursor, model._meta.db_table
                    )
                }
                if "version" not in columns:
                    editor.add_field(model, model._meta.get_field("version"))
            if OutboxEvent._meta.db_table not in tables:
                editor.create_model(OutboxEvent)
