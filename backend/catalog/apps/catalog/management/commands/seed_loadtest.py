import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.seeding import owner_email, seed_catalog


class Command(BaseCommand):
    help = (
        "Seed load-test owners (loadtest-<n>@example.com) with questionnaire and "
        "battery types (#9). Then run instances' seed_loadtest, which reads the copies "
        "these events create. Runs only under DEBUG or the loadtest settings."
    )

    def add_arguments(self, parser):
        parser.add_argument("--owners", type=int, default=5)
        parser.add_argument(
            "--password",
            default=os.environ.get("LOADTEST_OWNER_PASSWORD"),
            help="Owner password (default: $LOADTEST_OWNER_PASSWORD).",
        )

    def handle(self, *args, **options):  # noqa: ARG002
        # Owners with a known password must never land on a real deploy.
        if not (settings.DEBUG or getattr(settings, "LOADTEST", False)):
            raise CommandError("seed_loadtest runs only under DEBUG or loadtest.")
        if not options["password"]:
            raise CommandError("Set --password or LOADTEST_OWNER_PASSWORD.")
        result = seed_catalog(owners=options["owners"], password=options["password"])
        self.stdout.write(
            f"owners: {result.owners_created} created, "
            f"{result.owners_skipped} already there "
            f"({owner_email(0)} … {owner_email(options['owners'] - 1)})\n"
            f"questionnaire types: {result.questionnaire_types}"
        )
