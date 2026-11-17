"""`instances`' commands (#43, #45), on .NET and on Go (#52).

`seed-loadtest` must give every load-test owner the shape Django's `seed_loadtest`
gave (compared side by side until #45 removed it): 100 rows per owner, 20 of them in
10 batteries, most submitted, spread over 90 days. `reconcile-refs` must repair copies
from the parity suite's stub `catalog`. Each test runs against both binaries.
Throwaway Postgres; skips without Docker, and each binary without its toolchain.
"""

import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from test_go_schema import go
from test_go_schema import go_service as go_service
from test_instances_schema import (  # Fixtures and helpers, not tests.
    BACKEND,
    docker_available,
    dotnet,
    run,
)
from test_instances_schema import postgres as postgres
from test_instances_schema import service as dotnet_service  # noqa: F401 (fixture)

sys.path.insert(0, str(BACKEND))
from parity_instances.stub_catalog import StubCatalog
from parity_instances.support import qtype_snapshot

OWNERS = 3
PER_OWNER = 100

pytestmark = pytest.mark.skipif(not docker_available(), reason="needs Docker")


@pytest.fixture(params=["dotnet", "go"])
def service(request) -> list[str]:
    """The binary under test: .NET's `Instances.Api.dll`, or Go's `instances`."""
    if request.param == "dotnet":
        if dotnet() is None:
            pytest.skip("needs the .NET SDK")
        return request.getfixturevalue("dotnet_service")
    if go() is None:
        pytest.skip("needs Go")
    return request.getfixturevalue("go_service")


def create_database(container: str, name: str) -> None:
    psql = ("docker", "exec", container, "psql", "-U", "postgres", "-qc")
    run(*psql, f"CREATE DATABASE {name}")


def add_copy(url: str, owner: uuid.UUID, title: str, version: int = 1, ref=None):
    """A questionnaire type's copy, as an event from `catalog` would leave it."""
    ref = ref or uuid.uuid4()
    now = datetime.now(UTC)
    with psycopg.connect(url) as connection:
        connection.execute(
            "INSERT INTO questionnaires_questionnairetyperef"
            " (id, title, created_at, updated_at, version, owner_id,"
            " questionnaire_json)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
            [ref, title, now, now, version, owner, json.dumps({"pages": []})],
        )
    return ref


def add_load_test_owner(url: str, owner: uuid.UUID) -> None:
    """What `catalog`'s seeder sends for one owner: three scales and a battery."""
    scales = [add_copy(url, owner, f"Scale {n}") for n in (1, 2, 3)]
    battery = uuid.uuid4()
    now = datetime.now(UTC)
    with psycopg.connect(url) as connection:
        connection.execute(
            "INSERT INTO questionnaires_batterytyperef"
            " (id, title, created_at, updated_at, version, owner_id, description)"
            " VALUES (%s, 'Intake battery', %s, %s, 1, %s, '')",
            [battery, now, now, owner],
        )
        for order, scale in enumerate(scales[:2]):
            connection.execute(
                "INSERT INTO questionnaires_batterytyperefslot"
                ' (battery_type_id, questionnaire_type_id, "order")'
                " VALUES (%s, %s, %s)",
                [battery, scale, order],
            )


def shape(url: str) -> dict:
    """Per owner: rows, battery rows, batteries, submitted, oldest and newest."""
    with psycopg.connect(url) as connection:
        rows = connection.execute(
            "SELECT q.owner_id, count(*), count(q.battery_id), count(q.submitted_at),"
            " min(q.created_at), max(q.created_at),"
            " bool_and(q.submitted_at IS NULL OR q.submitted_at >= q.created_at),"
            " (SELECT count(*) FROM questionnaires_battery b"
            "  WHERE b.owner_id = q.owner_id)"
            " FROM questionnaires_questionnaire q GROUP BY q.owner_id ORDER BY 1"
        ).fetchall()
    return {row[0]: row[1:] for row in rows}


def test_the_seeder_gives_the_load_test_shape(postgres, service):
    container, base = postgres
    name = f"seed_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{name}"
    create_database(container, name)
    env = {**os.environ, "SETTINGS": "dev", "INSTANCES_DATABASE_URL": url}
    run(*service, "migrate", env=env)
    owners = [uuid.UUID(int=n + 1) for n in range(OWNERS)]
    for owner in owners:
        add_load_test_owner(url, owner)

    count = ("--questionnaires-per-owner", str(PER_OWNER))
    seeded = run(*service, "seed-loadtest", *count, env=env)
    assert f"owners: {OWNERS} seeded, 0 already there" in seeded.stdout

    now = datetime.now(UTC)
    found = shape(url)
    assert list(found) == owners
    for owner in owners:
        rows, in_batteries, submitted, oldest, newest, ordered, batteries = found[owner]
        assert (rows, in_batteries, batteries) == (PER_OWNER, 20, 10)
        assert 50 <= submitted <= 90
        assert now - timedelta(days=90, minutes=5) <= oldest <= newest <= now
        assert ordered

    # An owner who already has rows is left alone.
    again = run(*service, "seed-loadtest", *count, env=env)
    assert f"owners: 0 seeded, {OWNERS} already there" in again.stdout


def test_seeding_is_refused_outside_dev_and_loadtest(postgres, service):
    _container, base = postgres
    env = {**os.environ, "SETTINGS": "test", "INSTANCES_DATABASE_URL": f"{base}/x"}
    result = subprocess.run(  # noqa: S603
        [*service, "seed-loadtest"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "only under dev or loadtest" in result.stderr


def test_reconcile_repairs_from_the_stub_catalog(postgres, service):
    container, base = postgres
    name = f"reconcile_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{name}"
    create_database(container, name)
    env = {**os.environ, "SETTINGS": "test", "INSTANCES_DATABASE_URL": url}
    run(*service, "migrate", env=env)
    owner = uuid.uuid4()
    stale = add_copy(url, owner, "Old", version=1)
    gone = add_copy(url, owner, "Gone")
    missing = uuid.uuid4()

    with StubCatalog() as stub:
        newer = qtype_snapshot(str(owner), ref_id=str(stale), version=2, title="New")
        stub.add(newer)
        stub.add(qtype_snapshot(str(owner), ref_id=str(missing), title="Missing"))
        env["CATALOG_INTERNAL_URL"] = stub.url
        dry = run(*service, "reconcile-refs", "--dry-run", env=env)
        result = run(*service, "reconcile-refs", env=env)
        again = run(*service, "reconcile-refs", env=env)
        assert all(
            r.authorization == "Bearer test-instances-to-catalog" for r in stub.requests
        )

    assert dry.stdout == result.stdout
    assert result.stdout.splitlines() == [
        "created: 1",
        f"  questionnaire_type {missing}",
        "updated: 1",
        f"  questionnaire_type {stale}",
        "removed: 1",
        f"  questionnaire_type {gone}",
        "orphans_in_use: 0",
    ]
    assert "created: 0" in again.stdout
    assert "removed: 0" in again.stdout
    with psycopg.connect(url) as connection:
        titles = dict(
            connection.execute(
                "SELECT id, title FROM questionnaires_questionnairetyperef"
            ).fetchall()
        )
    assert titles == {stale: "New", missing: "Missing"}
