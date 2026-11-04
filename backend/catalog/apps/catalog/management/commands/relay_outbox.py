import time

from django.core.management.base import BaseCommand

from apps.catalog import events


class Command(BaseCommand):
    help = (
        "Retry undelivered type events until they reach instances (#13). "
        "Runs until stopped, or one pass with --once."
    )

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=float, default=5.0)

    def handle(self, *args, **options):  # noqa: ARG002
        while True:
            delivered, pending = events.deliver_pending()
            events.prune_delivered()
            if options["once"]:
                self.stdout.write(f"delivered: {delivered}, pending: {pending}")
                return
            if delivered or pending:
                self.stdout.write(f"delivered: {delivered}, pending: {pending}")
            time.sleep(options["interval"])
