import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.questionnaires.seeding import owner_email, seed_loadtest


class Command(BaseCommand):
    help = (
        "Seed load-test owners (loadtest-<n>@example.com) with questionnaire "
        "types, batteries and questionnaires spread over 90 days (#9). "
        "Runs only under DEBUG or the loadtest settings."
    )

    def add_arguments(self, parser):
        parser.add_argument("--owners", type=int, default=5)
        parser.add_argument("--questionnaires-per-owner", type=int, default=200)
        parser.add_argument("--seed", type=int, default=1234)
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
        result = seed_loadtest(
            owners=options["owners"],
            questionnaires_per_owner=options["questionnaires_per_owner"],
            password=options["password"],
            seed=options["seed"],
        )
        self.stdout.write(
            f"owners: {result.owners_created} created, "
            f"{result.owners_skipped} already there "
            f"({owner_email(0)} … {owner_email(options['owners'] - 1)})\n"
            f"questionnaire types: {result.questionnaire_types}, "
            f"batteries: {result.batteries}, "
            f"questionnaires: {result.questionnaires} "
            f"({result.submitted} submitted)"
        )
