"""What `catalog` does over HTTP, whichever framework serves it (#34).

The suite starts the service under test as a real server, next to a stub `instances`,
and talks to both only over HTTP. It imports no service code, so the same tests check
the Django version and the FastAPI one (#35).

    cd backend && uv run pytest parity --target=django
"""

import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import pytest

from .stub_instances import StubInstances, free_port

BACKEND = Path(__file__).resolve().parent.parent
INSTANCES_TO_CATALOG_TOKEN = "test-instances-to-catalog"
CATALOG_TO_INSTANCES_TOKEN = "test-catalog-to-instances"
PASSWORD = "parity-pass-123"


def _django(port: int) -> tuple[list[list[str]], dict]:
    manage = [sys.executable, "catalog/manage.py"]
    return (
        [
            [*manage, "migrate", "--noinput"],
            [*manage, "runserver", f"127.0.0.1:{port}", "--noreload"],
        ],
        {"DJANGO_SETTINGS_MODULE": "core.settings.parity"},
    )


def _fastapi(port: int) -> tuple[list[list[str]], dict]:
    return (
        [
            [sys.executable, "-m", "catalog_fastapi", "migrate"],
            [
                sys.executable,
                "-m",
                "uvicorn",
                "catalog_fastapi.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
        ],
        {"SETTINGS": "parity"},
    )


TARGETS = {"django": _django, "fastapi": _fastapi}


def pytest_addoption(parser):
    parser.addoption(
        "--target",
        choices=sorted(TARGETS),
        default="django",
        help="Which catalog implementation to start and test.",
    )


@pytest.fixture(scope="session")
def stub():
    with StubInstances() as server:
        yield server


@pytest.fixture(autouse=True)
def _reset_stub(stub):
    stub.retire_status = 204
    stub.events_status = 200


def _wait_until_up(url: str, process: subprocess.Popen, log: Path) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.exit(f"catalog exited during start:\n{log.read_text()}", 1)
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    process.kill()
    pytest.exit(f"catalog did not start in 60 s:\n{log.read_text()}", 1)


@pytest.fixture(scope="session")
def base_url(request, stub):
    target = request.config.getoption("--target")
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="parity-") as tmp:
        commands, extra_env = TARGETS[target](port)
        env = {
            **os.environ,
            **extra_env,
            "PARITY_DATABASE": str(Path(tmp) / "catalog.sqlite3"),
            "PARITY_INSTANCES_URL": stub.url,
        }
        log = Path(tmp) / "server.log"
        with log.open("w") as out:
            for command in commands[:-1]:
                subprocess.run(  # noqa: S603 (fixed commands from TARGETS)
                    command, cwd=BACKEND, env=env, stdout=out, stderr=out, check=True
                )
            # Its own session, so the stop below also reaches a reloader's child.
            process = subprocess.Popen(  # noqa: S603
                commands[-1],
                cwd=BACKEND,
                env=env,
                stdout=out,
                stderr=out,
                start_new_session=True,
            )
        url = f"http://127.0.0.1:{port}"
        try:
            _wait_until_up(f"{url}/internal/health/", process, log)
            yield url
        finally:
            os.killpg(process.pid, 15)
            process.wait(timeout=10)


@pytest.fixture
def client(base_url):
    with httpx.Client(base_url=base_url, timeout=10) as http:
        yield http


def unique_email() -> str:
    return f"parity-{uuid.uuid4().hex[:12]}@example.com"


def register(client: httpx.Client, email: str | None = None) -> dict:
    email = email or unique_email()
    response = client.post(
        "/api/accounts/register/", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return {**response.json(), "password": PASSWORD}


def login(client: httpx.Client, email: str) -> dict:
    response = client.post("/api/token/", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def owner(client):
    """A fresh user, and a client that sends their access token."""
    user = register(client)
    tokens = login(client, user["email"])
    client.headers["Authorization"] = f"Bearer {tokens['access']}"
    return user


@pytest.fixture
def other_client(base_url):
    """A second owner, for isolation checks."""
    with httpx.Client(base_url=base_url, timeout=10) as http:
        user = register(http)
        tokens = login(http, user["email"])
        http.headers["Authorization"] = f"Bearer {tokens['access']}"
        yield http


@pytest.fixture
def internal(base_url):
    """What `instances` sends to `catalog`'s /internal/."""
    with httpx.Client(
        base_url=base_url,
        timeout=10,
        headers={"Authorization": f"Bearer {INSTANCES_TO_CATALOG_TOKEN}"},
    ) as http:
        yield http
