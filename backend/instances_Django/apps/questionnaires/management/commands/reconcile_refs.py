from django.core.management.base import BaseCommand

from apps.questionnaires import refs


class Command(BaseCommand):
    help = (
        "Rebuild or repair every copy of a type from catalog, and report the "
        "differences (#13). Use it after a data move or a long outage."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Report only, change nothing."
        )

    def handle(self, *args, **options):  # noqa: ARG002
        report = refs.reconcile(dry_run=options["dry_run"])
        for name in ("created", "updated", "removed", "orphans_in_use"):
            rows = getattr(report, name)
            self.stdout.write(f"{name}: {len(rows)}")
            for row in rows:
                self.stdout.write(f"  {row}")
