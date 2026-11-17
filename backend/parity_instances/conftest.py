"""What `instances` does over HTTP, as the SPA, respondents and `catalog` use it (#40).

The suite starts `instances` as a real server next to a stub `catalog`, and talks to
both only over HTTP. It imports no service code, so it checks either implementation
(#42, #51), chosen by INSTANCES_IMPL:

    cd backend && uv run pytest parity_instances                        # .NET
    cd backend && INSTANCES_IMPL=django uv run pytest parity_instances  # Django
    cd backend && INSTANCES_IMPL=go uv run pytest parity_instances      # Go

.NET is built from `backend/instances_NET`; Django runs from `backend/instances_Django`
under gunicorn; Go is built from `backend/instances_GO` (#52). Each runs on a throwaway
Postgres in Docker. The one thing the suite
does outside HTTP is move rows in time for the dashboard tests (`support.Clock`).
"""

import contextlib
import ctypes
import os
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from .stub_catalog import StubCatalog, free_port
from .support import (
    CATALOG_TO_INSTANCES_TOKEN,
    Catalog,
    Clock,
    Owner,
    new_id,
    token,
)

BACKEND = Path(__file__).resolve().parent.parent
DOTNET_PROJECT = BACKEND / "instances_NET" / "src" / "Instances.Api"
DJANGO_PROJECT = BACKEND / "instances_Django"
GO_MODULE = BACKEND / "instances_GO"
IMPLEMENTATIONS = ("dotnet", "django", "go")
# One gthread worker; `--bind` is added per run.
GUNICORN = ("--config", "/dev/null", "--worker-class", "gthread", "--threads", "4")
POSTGRES_IMAGE = "postgres:16-alpine"
SPA_ORIGIN = "http://localhost:5174"


@dataclass
class Server:
    commands: list[list[str]]
    cwd: Path
    env: dict[str, str]
    database: str


def _dotnet_cli() -> str:
    found = shutil.which("dotnet") or str(Path.home() / ".dotnet" / "dotnet")
    if not Path(found).exists():
        raise pytest.UsageError("instances needs the .NET SDK (see README)")
    return found


def _run(*argv: str) -> str:
    return subprocess.run(argv, check=True, capture_output=True, text=True).stdout  # noqa: S603


@contextlib.contextmanager
def _postgres() -> Iterator[str]:
    """A throwaway Postgres in Docker, on a free port, gone when the session ends."""
    name = f"parity-instances-{uuid.uuid4().hex[:8]}"
    _run(
        "docker", "run", "--rm", "-d", "--name", name,
        "--tmpfs", "/var/lib/postgresql/data",
        "-e", "POSTGRES_PASSWORD=throwaway", "-e", "POSTGRES_DB=instances",
        "-p", "127.0.0.1::5432", POSTGRES_IMAGE,
    )  # fmt: skip
    try:
        published = _run("docker", "port", name, "5432/tcp").splitlines()[0]
        port = published.rsplit(":", 1)[1]
        # Over TCP: the image's init-time server listens only on its socket.
        ready = ("docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-q")
        for _ in range(120):
            if subprocess.run(ready, check=False).returncode == 0:  # noqa: S603
                break
            time.sleep(0.5)
        yield f"postgresql://postgres:throwaway@127.0.0.1:{port}/instances"
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)  # noqa: S603, S607


@contextlib.contextmanager
def _dotnet(port: int, tmp: Path, catalog_url: str) -> Iterator[Server]:
    dotnet = _dotnet_cli()
    out = tmp / "build"
    with _postgres() as database:
        dll = [dotnet, str(out / "Instances.Api.dll")]
        yield Server(
            commands=[
                [dotnet, "build", str(DOTNET_PROJECT), "-c", "Release", "-o", str(out)],
                [*dll, "migrate"],
                dll,
            ],
            cwd=DOTNET_PROJECT,
            env={
                "SETTINGS": "test",
                "INSTANCES_DATABASE_URL": database,
                "CATALOG_INTERNAL_URL": catalog_url,
                "CORS_ALLOWED_ORIGINS": SPA_ORIGIN,
                "ASPNETCORE_URLS": f"http://127.0.0.1:{port}",
                "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                "DOTNET_NOLOGO": "1",
                "Logging__LogLevel__Default": "Warning",
            },
            database=database,
        )


@contextlib.contextmanager
def _django(port: int, tmp: Path, catalog_url: str) -> Iterator[Server]:
    del tmp  # Nothing to build.
    python = shutil.which("python") or "python"
    bind = f"--bind=127.0.0.1:{port}"
    with _postgres() as database:
        yield Server(
            commands=[
                [python, "manage.py", "migrate", "--no-input", "-v", "0"],
                # Not the service's gunicorn.conf.py: no multiprocess metrics here.
                [python, "-m", "gunicorn", "core.wsgi:application", *GUNICORN, bind],
            ],
            cwd=DJANGO_PROJECT,
            env={
                "DJANGO_SETTINGS_MODULE": "core.settings.parity",
                "SECRET_KEY": "parity-instances-not-a-secret",
                "INSTANCES_DATABASE_URL": database,
                "CATALOG_INTERNAL_URL": catalog_url,
                "CORS_ALLOWED_ORIGINS": SPA_ORIGIN,
            },
            database=database,
        )


def _go_cli() -> str:
    found = shutil.which("go") or str(Path.home() / ".go" / "bin" / "go")
    if not Path(found).exists():
        raise pytest.UsageError("instances_GO needs Go (see README)")
    return found


@contextlib.contextmanager
def _go(port: int, tmp: Path, catalog_url: str) -> Iterator[Server]:
    binary = str(tmp / "instances")
    with _postgres() as database:
        yield Server(
            commands=[
                [_go_cli(), "build", "-o", binary, "./cmd/instances"],
                [binary, "migrate"],
                [binary],
            ],
            cwd=GO_MODULE,
            env={
                "SETTINGS": "test",
                "INSTANCES_DATABASE_URL": database,
                "CATALOG_INTERNAL_URL": catalog_url,
                "CORS_ALLOWED_ORIGINS": SPA_ORIGIN,
                "ASPNETCORE_URLS": f"http://127.0.0.1:{port}",
                "GOTOOLCHAIN": "local",
            },
            database=database,
        )


def _implementation() -> str:
    impl = os.environ.get("INSTANCES_IMPL", "dotnet")
    if impl not in IMPLEMENTATIONS:
        raise pytest.UsageError(f"INSTANCES_IMPL={impl!r}: one of {IMPLEMENTATIONS}")
    return impl


def _die_with_parent() -> None:
    """Linux: the server gets SIGTERM if pytest dies, even by SIGKILL."""
    pr_set_pdeathsig = 1
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(pr_set_pdeathsig, signal.SIGTERM)


def _wait_until_up(url: str, process: subprocess.Popen, log: Path) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.exit(f"instances exited during start:\n{log.read_text()}", 1)
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    os.killpg(process.pid, signal.SIGKILL)
    pytest.exit(f"instances did not start in 120 s:\n{log.read_text()}", 1)


@pytest.fixture(scope="session")
def stub() -> Iterator[StubCatalog]:
    with StubCatalog() as server:
        yield server


@pytest.fixture(autouse=True)
def _reset_stub(stub):
    stub.reset()


@pytest.fixture(scope="session")
def server(stub) -> Iterator[tuple[str, str]]:
    """The base URL and database of a fresh `instances`, for the whole session."""
    port = free_port()
    with (
        tempfile.TemporaryDirectory(prefix="parity-instances-") as tmp,
        {"dotnet": _dotnet, "django": _django, "go": _go}[_implementation()](
            port, Path(tmp), stub.url
        ) as spec,
    ):
        yield from _serve(spec, port, Path(tmp))


def _serve(spec: Server, port: int, tmp: Path) -> Iterator[tuple[str, str]]:
    env = {**os.environ, **spec.env}
    log = tmp / "server.log"
    with log.open("w") as out:
        for command in spec.commands[:-1]:
            done = subprocess.run(  # noqa: S603 (fixed commands)
                command, cwd=spec.cwd, env=env, stdout=out, stderr=out, check=False
            )
            if done.returncode:
                pytest.exit(f"{command} failed:\n{log.read_text()}", 1)
        # Its own session, so the stop below reaches any child it starts.
        process = subprocess.Popen(  # noqa: S603
            spec.commands[-1],
            cwd=spec.cwd,
            env=env,
            stdout=out,
            stderr=out,
            start_new_session=True,
            preexec_fn=_die_with_parent,  # noqa: PLW1509 (no threads yet)
        )
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_up(f"{url}/internal/health/", process, log)
        yield url, spec.database
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)


@pytest.fixture(scope="session")
def base_url(server) -> str:
    return server[0]


@pytest.fixture(scope="session")
def clock(server) -> Clock:
    return Clock(server[1])


def _client(base_url: str, bearer: str | None = None) -> httpx.Client:
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return httpx.Client(base_url=base_url, timeout=30, headers=headers)


@pytest.fixture
def anon(base_url) -> Iterator[httpx.Client]:
    """A respondent: no token at all."""
    with _client(base_url) as http:
        yield http


@pytest.fixture
def catalog(base_url) -> Iterator[Catalog]:
    """What `catalog` sends to `/internal/`."""
    with _client(base_url, CATALOG_TO_INSTANCES_TOKEN) as http:
        yield Catalog(http)


def _owner(base_url: str) -> Iterator[Owner]:
    owner_id = new_id()
    with _client(base_url, token(owner_id)) as http:
        yield Owner(owner_id, http)


@pytest.fixture
def owner(base_url) -> Iterator[Owner]:
    """A fresh owner. No user row is needed: the token is all `instances` checks."""
    yield from _owner(base_url)


@pytest.fixture
def other(base_url) -> Iterator[Owner]:
    """A second owner, for isolation checks."""
    yield from _owner(base_url)


@pytest.fixture
def qtype(catalog, owner) -> dict:
    """A questionnaire type of `owner`'s that has arrived."""
    return catalog.qtype(owner)
