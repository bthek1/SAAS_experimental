from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.questionnaires.seeding import seed_instances


class Command(BaseCommand):
    help = (
        "Create batteries and questionnaires spread over 90 days for every load-test "
        "owner whose types have reached this service (#9). Run catalog's seed_loadtest "
        "first. Runs only under DEBUG or the loadtest settings."
    )

    def add_arguments(self, parser):
        parser.add_argument("--questionnaires-per-owner", type=int, default=200)
        parser.add_argument("--seed", type=int, default=1234)

    def handle(self, *args, **options):  # noqa: ARG002
        if not (settings.DEBUG or getattr(settings, "LOADTEST", False)):
            raise CommandError("seed_loadtest runs only under DEBUG or loadtest.")
        result = seed_instances(
            questionnaires_per_owner=options["questionnaires_per_owner"],
            seed=options["seed"],
        )
        self.stdout.write(
            f"owners: {result.owners_seeded} seeded, "
            f"{result.owners_skipped} already there\n"
            f"batteries: {result.batteries}, "
            f"questionnaires: {result.questionnaires} "
            f"({result.submitted} submitted)"
        )
