"""Operational commands (#35, #36).

    uv run python -m catalog <command> [options]

migrate          apply Alembic migrations; a Django-built database is stamped at
                 the baseline first
reset-db         empty this service's tables (debug or loadtest only)
clear-cache      empty the cache's Redis database
relay-outbox     retry undelivered events until stopped, or once with `--once`
seed-loadtest    load-test owners and types, under debug or loadtest only
create-superuser a staff superuser from DJANGO_SUPERUSER_EMAIL and _PASSWORD
"""

import argparse
import os
import sys
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from rich.console import Console
from sqlalchemy import exists, inspect, select

from catalog import cache, events
from catalog.auth import make_password
from catalog.db import get_engine, session_factory
from catalog.models import DJANGO_USER_LINKS, Base, User
from catalog.seeding import owner_email, seed_catalog
from catalog.settings import get_settings

console = Console()
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def fail(message: str) -> None:
    console.print(f"[red]error:[/] {message}")
    sys.exit(1)


def migrate(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Upgrade to head. A database Django built is stamped at the baseline first."""
    config = Config(str(ALEMBIC_INI))
    with get_engine().connect() as connection:
        inspector = inspect(connection)
        built_by_django = not inspector.has_table(
            "alembic_version"
        ) and inspector.has_table(User.__tablename__)
    if built_by_django:
        command.stamp(config, "0001")
        console.print("[green]adopted[/] the schema Django built, as revision 0001")
    command.upgrade(config, "head")
    console.print("[green]migrated[/] to head")


def reset_db(args: argparse.Namespace) -> None:
    """Empty this service's tables, as Django's `flush` did (`just loadtest-reset`)."""
    if not (get_settings().debug or get_settings().loadtest) and not args.force:
        fail("reset-db runs only under debug or loadtest (or with --force).")
    with session_factory()() as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        for table in DJANGO_USER_LINKS:
            connection = session.connection()
            if connection.dialect.has_table(connection, table.name):
                session.execute(table.delete())
        session.commit()
    console.print("[green]emptied[/] " + ", ".join(Base.metadata.tables))


def clear_cache(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Empty the cache's Redis database, as Django's `cache.clear()` did."""
    cache.client().flushdb()
    console.print("[green]cleared[/] the cache")


def relay_outbox(args: argparse.Namespace) -> None:
    while True:
        with session_factory()() as session:
            delivered, pending = events.deliver_pending(session)
            events.prune_delivered(session)
        if args.once or delivered or pending:
            console.print(f"delivered: {delivered}, pending: {pending}")
        if args.once:
            return
        time.sleep(args.interval)


def seed_loadtest(args: argparse.Namespace) -> None:
    settings = get_settings()
    # Owners with a known password must never land on a real deploy.
    if not (settings.debug or settings.loadtest):
        fail("seed-loadtest runs only under debug or loadtest.")
    if not args.password:
        fail("Set --password or LOADTEST_OWNER_PASSWORD.")
    with session_factory()() as session:
        result = seed_catalog(session, owners=args.owners, password=args.password)
    console.print(
        f"owners: {result.owners_created} created, {result.owners_skipped} already "
        f"there ({owner_email(0)} ... {owner_email(args.owners - 1)})\n"
        f"questionnaire types: {result.questionnaire_types}"
    )


def create_superuser(args: argparse.Namespace) -> None:  # noqa: ARG001
    email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
    if not (email and password):
        fail("Set DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD.")
    with session_factory()() as session:
        if session.scalar(select(exists().where(User.email == email))):
            fail(f"{email} already exists.")
        session.add(
            User(
                email=email,
                password=make_password(password),
                is_staff=True,
                is_superuser=True,
            )
        )
        session.commit()
    console.print(f"[green]superuser created:[/] {email}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m catalog")
    commands = parser.add_subparsers(dest="command", required=True)

    sub = commands.add_parser("migrate", help="apply Alembic migrations")
    sub.set_defaults(run=migrate)

    sub = commands.add_parser("reset-db", help="empty this service's tables")
    sub.add_argument("--force", action="store_true", help="outside debug/loadtest")
    sub.set_defaults(run=reset_db)

    sub = commands.add_parser("clear-cache", help="empty the cache's Redis db")
    sub.set_defaults(run=clear_cache)

    sub = commands.add_parser("relay-outbox", help="retry undelivered events")
    sub.add_argument("--once", action="store_true")
    sub.add_argument("--interval", type=float, default=5.0)
    sub.set_defaults(run=relay_outbox)

    sub = commands.add_parser("seed-loadtest", help="load-test owners and types")
    sub.add_argument("--owners", type=int, default=5)
    sub.add_argument(
        "--password",
        default=os.environ.get("LOADTEST_OWNER_PASSWORD"),
        help="owner password (default: $LOADTEST_OWNER_PASSWORD)",
    )
    sub.set_defaults(run=seed_loadtest)

    sub = commands.add_parser("create-superuser", help="from DJANGO_SUPERUSER_*")
    sub.set_defaults(run=create_superuser)

    args = parser.parse_args(argv)
    args.run(args)


if __name__ == "__main__":
    main()
