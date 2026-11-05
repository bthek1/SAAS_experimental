"""`import_from_monolith` against real Postgres (#13). It uses COPY, so SQLite can't.

Runs in a throwaway container with its own port, so it never touches the dev stack.
The source schema below is deliberately frozen: it is what `main` left behind before
the split, and databases of that age won't change. Skips when Docker isn't available.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parent.parent
IMAGE = "postgres:16-alpine"
PASSWORD = "throwaway"

MONOLITH_SCHEMA = """
CREATE TABLE accounts_customuser (id uuid PRIMARY KEY, is_active boolean NOT NULL);
CREATE TABLE questionnaires_questionnairetype (
    id uuid PRIMARY KEY, title varchar(255) NOT NULL, created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL, owner_id uuid NOT NULL,
    questionnaire_json jsonb NOT NULL);
CREATE TABLE questionnaires_batterytype (
    id uuid PRIMARY KEY, title varchar(255) NOT NULL, created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL, owner_id uuid NOT NULL, description text NOT NULL);
CREATE TABLE questionnaires_batterytypeitem (
    id bigserial PRIMARY KEY, battery_type_id uuid NOT NULL,
    questionnaire_type_id uuid NOT NULL, "order" integer NOT NULL);
CREATE TABLE questionnaires_battery (
    id uuid PRIMARY KEY, created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL, owner_id uuid NOT NULL,
    battery_type_id uuid NOT NULL, name varchar(255) NOT NULL,
    share_token uuid NOT NULL);
CREATE TABLE questionnaires_questionnaire (
    id uuid PRIMARY KEY, created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL, owner_id uuid NOT NULL,
    questionnaire_type_id uuid NOT NULL, battery_id uuid, battery_order integer,
    name varchar(255) NOT NULL, share_token uuid NOT NULL, answers_json jsonb NOT NULL,
    questionnaire_json_snapshot jsonb NOT NULL, metrics_json jsonb NOT NULL,
    submitted_at timestamptz);
"""
NOW = "2026-01-02 03:04:05+00"
ACTIVE, INACTIVE = uuid.uuid4(), uuid.uuid4()
QTYPE, BTYPE, BATTERY, QUESTIONNAIRE = (uuid.uuid4() for _ in range(4))
ANSWERS = {"q1": 3, "note": "tab\tand \\ backslash"}


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    info = subprocess.run(["docker", "info"], check=False, capture_output=True)  # noqa: S607
    return info.returncode == 0


pytestmark = pytest.mark.skipif(not docker_available(), reason="needs Docker")


@pytest.fixture(scope="module")
def server():
    """A Postgres of our own: no volume, a port Docker picks, loopback only."""
    name = f"saas-import-test-{uuid.uuid4().hex[:8]}"
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "docker", "run", "--rm", "-d", "--name", name,
            "--tmpfs", "/var/lib/postgresql/data",
            "-e", f"POSTGRES_PASSWORD={PASSWORD}",
            "-p", "127.0.0.1::5432", IMAGE,
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    try:
        port = (
            subprocess.run(  # noqa: S603
                ["docker", "port", name, "5432/tcp"],  # noqa: S607
                check=True,
                capture_output=True,
                text=True,
            )
            .stdout.splitlines()[0]
            .rsplit(":", 1)[1]
        )
        base = f"postgresql://postgres:{PASSWORD}@127.0.0.1:{port}"
        # initdb's temporary server takes no TCP, so a connection means the real one.
        for _ in range(60):
            try:
                psycopg.connect(f"{base}/postgres", connect_timeout=2).close()
                break
            except psycopg.OperationalError:
                time.sleep(0.5)
        else:
            pytest.fail("Postgres did not start")
        yield base
    finally:
        subprocess.run(  # noqa: S603
            ["docker", "stop", "-t", "0", name],  # noqa: S607
            check=False,
            capture_output=True,
        )


def create_database(server: str, name: str) -> str:
    with psycopg.connect(f"{server}/postgres", autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    return f"{server}/{name}"


def manage(destination: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [sys.executable, "instances/manage.py", *args],
        check=False,
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "core.settings.dev",
            "INSTANCES_DATABASE_URL": destination,
            "CACHE_ENABLED": "false",
        },
    )


def seed(source: str, *, version: bool = False) -> None:
    with psycopg.connect(source) as db:
        db.execute(MONOLITH_SCHEMA)
        if version:
            for table in ("questionnairetype", "batterytype"):
                db.execute(
                    f"ALTER TABLE questionnaires_{table} "
                    "ADD COLUMN version bigint NOT NULL DEFAULT 7"
                )
        db.execute(
            "INSERT INTO accounts_customuser VALUES (%s, true), (%s, false)",
            (ACTIVE, INACTIVE),
        )
        db.execute(
            "INSERT INTO questionnaires_questionnairetype "
            "(id, title, created_at, updated_at, owner_id, questionnaire_json) "
            "VALUES (%s, 'Type', %s, %s, %s, %s)",
            (QTYPE, NOW, NOW, ACTIVE, json.dumps({"pages": ["p1"]})),
        )
        db.execute(
            "INSERT INTO questionnaires_batterytype "
            "(id, title, created_at, updated_at, owner_id, description) "
            "VALUES (%s, 'Bundle', %s, %s, %s, 'Two lines\nof text')",
            (BTYPE, NOW, NOW, ACTIVE),
        )
        db.execute(
            "INSERT INTO questionnaires_batterytypeitem "
            '(battery_type_id, questionnaire_type_id, "order") VALUES (%s, %s, 4)',
            (BTYPE, QTYPE),
        )
        db.execute(
            "INSERT INTO questionnaires_battery VALUES (%s, %s, %s, %s, %s, 'B', %s)",
            (BATTERY, NOW, NOW, ACTIVE, BTYPE, uuid.uuid4()),
        )
        db.execute(
            "INSERT INTO questionnaires_questionnaire VALUES "
            "(%s, %s, %s, %s, %s, %s, 1, 'Q', %s, %s, '{}', '{}', %s)",
            (
                QUESTIONNAIRE, NOW, NOW, ACTIVE, QTYPE, BATTERY, uuid.uuid4(),
                json.dumps(ANSWERS), NOW,
            ),
        )  # fmt: skip


@pytest.fixture
def databases(server):
    """(source, migrated empty destination), new for each test."""
    suffix = uuid.uuid4().hex[:8]
    source = create_database(server, f"old_{suffix}")
    destination = create_database(server, f"new_{suffix}")
    migrated = manage(destination, "migrate", "--no-input")
    assert migrated.returncode == 0, migrated.stderr
    return source, destination


def row(url: str, query: str):
    with psycopg.connect(url) as db:
        return db.execute(query).fetchone()


def test_copies_every_table_and_leaves_the_source_alone(databases):
    source, destination = databases
    seed(source)

    result = manage(destination, "import_from_monolith", "--source", source)

    assert result.returncode == 0, result.stderr
    assert row(
        destination,
        "SELECT title, version, owner_id, questionnaire_json "
        "FROM questionnaires_questionnairetyperef",
    ) == ("Type", 0, ACTIVE, {"pages": ["p1"]})
    assert row(
        destination, "SELECT description, version FROM questionnaires_batterytyperef"
    ) == ("Two lines\nof text", 0)
    assert row(
        destination,
        'SELECT battery_type_id, questionnaire_type_id, "order" '
        "FROM questionnaires_batterytyperefslot",
    ) == (BTYPE, QTYPE, 4)
    assert row(destination, "SELECT id, name FROM questionnaires_battery") == (
        BATTERY,
        "B",
    )
    copied = row(
        destination,
        "SELECT id, battery_id, answers_json, submitted_at IS NOT NULL "
        "FROM questionnaires_questionnaire",
    )
    assert copied == (QUESTIONNAIRE, BATTERY, ANSWERS, True)
    assert row(source, "SELECT count(*) FROM questionnaires_questionnaire") == (1,)


def test_only_deactivated_users_become_blocked(databases):
    source, destination = databases
    seed(source)

    manage(destination, "import_from_monolith", "--source", source)

    with psycopg.connect(destination) as db:
        rows = db.execute(
            "SELECT owner_id, blocked, deleted FROM questionnaires_blockedowner"
        ).fetchall()
    assert rows == [(INACTIVE, True, False)]


def test_keeps_versions_from_the_interim_migrations(databases):
    source, destination = databases
    seed(source, version=True)

    result = manage(destination, "import_from_monolith", "--source", source)

    assert result.returncode == 0, result.stderr
    assert row(
        destination, "SELECT version FROM questionnaires_questionnairetyperef"
    ) == (7,)


def test_refuses_a_database_that_already_has_rows(databases):
    source, destination = databases
    seed(source)
    manage(destination, "import_from_monolith", "--source", source)

    second = manage(destination, "import_from_monolith", "--source", source)

    assert second.returncode != 0
    assert "already has rows" in second.stderr
    assert row(destination, "SELECT count(*) FROM questionnaires_questionnaire") == (1,)


def test_a_failure_leaves_the_destination_empty(databases):
    """A questionnaire of a type that isn't there fails at commit, undoing the rest."""
    source, destination = databases
    seed(source)
    with psycopg.connect(source) as db:
        db.execute(
            "UPDATE questionnaires_questionnaire SET questionnaire_type_id = %s",
            (uuid.uuid4(),),
        )

    result = manage(destination, "import_from_monolith", "--source", source)

    assert result.returncode != 0
    assert row(
        destination, "SELECT count(*) FROM questionnaires_questionnairetyperef"
    ) == (0,)
