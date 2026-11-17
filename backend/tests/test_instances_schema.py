"""`instances` (.NET) runs on the schema Django built for it (#42, #45).

`instances_django_schema.txt` is that schema, from `pg_dump`, sorted line by line like
`catalog_django_schema.txt`. `instances_django_built.sql` is a whole database Django's
migrations built, dumped before #45 removed them (`6b47566` has them). The EF baseline
migration must build exactly the schema, a database Django built must be adopted rather
than rebuilt, and EF's model must have nothing left to migrate. Never regenerate either
file to make a test pass. Runs in a throwaway Postgres; skips without Docker or the SDK.
"""

import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
SNAPSHOT = Path(__file__).with_name("instances_django_schema.txt")
DJANGO_BUILT = Path(__file__).with_name("instances_django_built.sql")
SOLUTION = BACKEND / "instances_NET"
PROJECT = SOLUTION / "src" / "Instances.Api"
IMAGE = "postgres:16-alpine"
PASSWORD = "throwaway"


def dotnet() -> str | None:
    found = shutil.which("dotnet") or str(Path.home() / ".dotnet" / "dotnet")
    return found if Path(found).exists() else None


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    info = subprocess.run(["docker", "info"], check=False, capture_output=True)  # noqa: S607
    return info.returncode == 0


pytestmark = [
    pytest.mark.skipif(not docker_available(), reason="needs Docker"),
    pytest.mark.skipif(dotnet() is None, reason="needs the .NET SDK"),
]


def run(*argv: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=True, capture_output=True, text=True, **kwargs)  # noqa: S603


@pytest.fixture(scope="module")
def postgres():
    name = f"saas-instances-schema-{uuid.uuid4().hex[:8]}"
    run(
        "docker", "run", "--rm", "-d", "--name", name,
        "--tmpfs", "/var/lib/postgresql/data",
        "-e", f"POSTGRES_PASSWORD={PASSWORD}",
        "-p", "127.0.0.1::5432", IMAGE,
    )  # fmt: skip
    try:
        port = run("docker", "port", name, "5432/tcp").stdout.splitlines()[0]
        port = port.rsplit(":", 1)[1]
        ready = ("docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-q")
        for _ in range(120):
            if subprocess.run(ready, check=False).returncode == 0:  # noqa: S603
                break
            time.sleep(0.5)
        psql = ("docker", "exec", name, "psql", "-U", "postgres", "-qc")
        for database in ("efbuilt", "djangobuilt", "adopted"):
            run(*psql, f"CREATE DATABASE {database}")
        yield name, f"postgres://postgres:{PASSWORD}@127.0.0.1:{port}"
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)  # noqa: S603, S607


@pytest.fixture(scope="module")
def service(tmp_path_factory) -> list[str]:
    """The built service, run as `dotnet Instances.Api.dll <command>`."""
    out = tmp_path_factory.mktemp("instances")
    run(dotnet(), "build", str(PROJECT), "-c", "Release", "-o", str(out))
    return [dotnet(), str(out / "Instances.Api.dll")]


def schema(container: str, database: str) -> list[str]:
    pg_dump = ("docker", "exec", container, "pg_dump", "-U", "postgres", "-s")
    dump = run(*pg_dump, "-t", "questionnaires_*", database)
    lines = (line.strip().rstrip(",") for line in dump.stdout.splitlines())
    return sorted(
        line
        for line in lines
        if line and not line.startswith(("--", "SET ", "SELECT ", "\\"))
    )


def dotnet_env(url: str) -> dict:
    return {**os.environ, "SETTINGS": "test", "INSTANCES_DATABASE_URL": url}


def test_the_ef_baseline_builds_the_schema_django_built(postgres, service):
    container, base = postgres
    result = run(*service, "migrate", env=dotnet_env(f"{base}/efbuilt"))
    assert "applied 20261113065646_Baseline" in result.stdout
    assert schema(container, "efbuilt") == SNAPSHOT.read_text().splitlines()


def load_django_built(container: str, database: str) -> None:
    load = ("docker", "exec", "-i", container, "psql", "-U", "postgres", "-q")
    run(*load, "-v", "ON_ERROR_STOP=1", "-d", database, input=DJANGO_BUILT.read_text())


def test_the_frozen_django_database_has_the_frozen_schema(postgres):
    container, _base = postgres
    load_django_built(container, "djangobuilt")
    assert schema(container, "djangobuilt") == SNAPSHOT.read_text().splitlines()


def test_a_database_django_built_is_adopted(postgres, service):
    container, base = postgres
    load_django_built(container, "adopted")
    env = dotnet_env(f"{base}/adopted")
    first = run(*service, "migrate", env=env)
    assert "adopted a database Django built" in first.stdout
    assert "no migrations to apply" in first.stdout
    again = run(*service, "migrate", env=env)
    assert "adopted" not in again.stdout
    assert schema(container, "adopted") == SNAPSHOT.read_text().splitlines()


def test_the_model_has_nothing_left_to_migrate():
    env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    run(dotnet(), "tool", "restore", cwd=SOLUTION, env=env)
    result = subprocess.run(  # noqa: S603
        [
            dotnet(),
            "ef",
            "migrations",
            "has-pending-model-changes",
            "--project",
            str(PROJECT),
        ],
        cwd=SOLUTION,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
