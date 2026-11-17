import psycopg
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.questionnaires.models import (
    Battery,
    BatteryTypeRef,
    BatteryTypeRefSlot,
    BlockedOwner,
    Questionnaire,
    QuestionnaireTypeRef,
)

Q_COLUMNS = (
    "id, created_at, updated_at, owner_id, questionnaire_type_id, battery_id, "
    "battery_order, name, share_token, answers_json, questionnaire_json_snapshot, "
    "metrics_json, submitted_at"
)
B_COLUMNS = "id, created_at, updated_at, owner_id, battery_type_id, name, share_token"


def copies(version: str) -> list[tuple]:
    """(model, destination columns, query on the old database), parents first."""
    common = f"id, title, created_at, updated_at, {version} AS version, owner_id"
    return [
        (
            QuestionnaireTypeRef,
            "id, title, created_at, updated_at, version, owner_id, questionnaire_json",
            (
                f"SELECT {common}, questionnaire_json "  # noqa: S608 - constants
                "FROM questionnaires_questionnairetype"
            ),
        ),
        (
            BatteryTypeRef,
            "id, title, created_at, updated_at, version, owner_id, description",
            (
                f"SELECT {common}, description "  # noqa: S608 - constants
                "FROM questionnaires_batterytype"
            ),
        ),
        (
            BatteryTypeRefSlot,
            'battery_type_id, questionnaire_type_id, "order"',
            (
                'SELECT battery_type_id, questionnaire_type_id, "order" '
                "FROM questionnaires_batterytypeitem"
            ),
        ),
        (
            BlockedOwner,
            "owner_id, blocked, deleted, version",
            "SELECT id, true, false, 1 FROM accounts_customuser WHERE NOT is_active",
        ),
        (Battery, B_COLUMNS, f"SELECT {B_COLUMNS} FROM questionnaires_battery"),  # noqa: S608
        (
            Questionnaire,
            Q_COLUMNS,
            f"SELECT {Q_COLUMNS} FROM questionnaires_questionnaire",  # noqa: S608
        ),
    ]


class Command(BaseCommand):
    help = (
        "Copy instance rows from a database from before the split into this service's "
        "empty database, and compare row counts (#13). Reads the source and never "
        "changes it. Postgres only. Run reconcile_refs afterwards."
    )

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True, help="Old database URL.")

    def handle(self, *args, **options):  # noqa: ARG002
        if Questionnaire.objects.exists() or QuestionnaireTypeRef.objects.exists():
            raise CommandError("This database already has rows. Nothing was copied.")
        with psycopg.connect(options["source"]) as source:
            source.read_only = True
            with transaction.atomic():
                for model, columns, query in copies(self._version_column(source)):
                    self._copy(source, model, columns, query)

    def _version_column(self, source) -> str:
        # Present only if the old database went through the interim migrations.
        found = source.execute(
            "SELECT 1 FROM information_schema.columns WHERE "
            "table_name = 'questionnaires_questionnairetype' "
            "AND column_name = 'version'"
        ).fetchone()
        return "version" if found else "0"

    def _copy(self, source, model, columns: str, query: str) -> None:
        table = model._meta.db_table
        with (
            source.cursor() as read,
            read.copy(f"COPY ({query}) TO STDOUT") as reader,
            connection.cursor() as write,
            write.cursor.copy(f"COPY {table} ({columns}) FROM STDIN") as writer,
        ):
            for block in reader:
                writer.write(block)
        expected = source.execute(f"SELECT count(*) FROM ({query}) AS s").fetchone()[0]  # noqa: S608
        actual = model.objects.count()
        if expected != actual:
            raise CommandError(f"{table}: {expected} rows in source, {actual} copied")
        self.stdout.write(f"{table}: {actual}")
