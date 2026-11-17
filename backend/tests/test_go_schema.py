"""instances_GO builds or adopts the schema Django built, and leaves it to .NET (#52).

The Go service never adds a migration: its `migrate` builds the baseline (the same DDL
as .NET's EF baseline) on an empty database, adopts a database Django built, and records
both in EF's own history table, so .NET can take over a database Go built. Compared with
the frozen `instances_django_schema.txt`, as `test_instances_schema.py` does for .NET.
Runs in a throwaway Postgres; skips without Docker or Go.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from test_instances_schema import (  # Fixtures and helpers, not tests.
    SNAPSHOT,
    docker_available,
    dotnet,
    load_django_built,
    run,
    schema,
)
from test_instances_schema import postgres as postgres
from test_instances_schema import service as service

BACKEND = Path(__file__).resolve().parent.parent
GO_MODULE = BACKEND / "instances_GO"


def go() -> str | None:
    found = shutil.which("go") or str(Path.home() / ".go" / "bin" / "go")
    return found if Path(found).exists() else None


pytestmark = [
    pytest.mark.skipif(not docker_available(), reason="needs Docker"),
    pytest.mark.skipif(go() is None, reason="needs Go"),
]


@pytest.fixture(scope="module")
def go_service(tmp_path_factory) -> list[str]:
    binary = tmp_path_factory.mktemp("instances_go") / "instances"
    env = {**os.environ, "GOTOOLCHAIN": "local"}
    run(go(), "build", "-o", str(binary), "./cmd/instances", cwd=GO_MODULE, env=env)
    return [str(binary)]


def create(container: str, database: str) -> None:
    psql = ("docker", "exec", container, "psql", "-U", "postgres", "-qc")
    run(*psql, f"CREATE DATABASE {database}")


def env(url: str) -> dict:
    return {**os.environ, "SETTINGS": "test", "INSTANCES_DATABASE_URL": url}


def test_go_builds_the_schema_django_built(postgres, go_service):
    container, base = postgres
    create(container, "gobuilt")
    result = run(*go_service, "migrate", env=env(f"{base}/gobuilt"))
    assert "applied 20261113065646_Baseline" in result.stdout
    assert schema(container, "gobuilt") == SNAPSHOT.read_text().splitlines()
    again = run(*go_service, "migrate", env=env(f"{base}/gobuilt"))
    assert "no migrations to apply" in again.stdout


def test_go_adopts_a_database_django_built(postgres, go_service):
    container, base = postgres
    create(container, "goadopted")
    load_django_built(container, "goadopted")
    first = run(*go_service, "migrate", env=env(f"{base}/goadopted"))
    assert "adopted a database Django built" in first.stdout
    again = run(*go_service, "migrate", env=env(f"{base}/goadopted"))
    assert "adopted" not in again.stdout
    assert schema(container, "goadopted") == SNAPSHOT.read_text().splitlines()


@pytest.mark.skipif(dotnet() is None, reason="needs the .NET SDK")
def test_dotnet_takes_over_a_database_go_built(postgres, go_service, service):
    container, base = postgres
    create(container, "handover")
    run(*go_service, "migrate", env=env(f"{base}/handover"))
    result = run(*service, "migrate", env=env(f"{base}/handover"))
    assert "adopted" not in result.stdout
    assert "no migrations to apply" in result.stdout


def test_go_refuses_a_database_newer_than_it_knows(postgres, go_service):
    container, base = postgres
    create(container, "newer")
    run(*go_service, "migrate", env=env(f"{base}/newer"))
    run(
        "docker", "exec", container, "psql", "-U", "postgres", "-d", "newer", "-qc",
        "INSERT INTO \"__EFMigrationsHistory\" VALUES ('20991231000000_Later', '10')",
    )  # fmt: skip
    refused = subprocess.run(  # noqa: S603
        [*go_service, "migrate"],
        env=env(f"{base}/newer"),
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0
    assert "20991231000000_Later" in refused.stderr
