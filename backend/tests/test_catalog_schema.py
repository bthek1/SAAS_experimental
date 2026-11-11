"""`catalog`'s migrations, against the schema Django built (#35, #38).

Revision 0001 is the schema Django's migrations left. Until #38 removed Django, this
test built both and compared them line for line. That comparison is now frozen in
`catalog_django_schema.txt`, taken from 0001 while the two still matched. Then: a
database Django built is adopted, and `alembic check` finds nothing for the models.
Runs in a throwaway Postgres, like test_import_from_monolith.py. Skips without
Docker.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
SNAPSHOT = Path(__file__).with_name("catalog_django_schema.txt")
IMAGE = "postgres:16-alpine"
PASSWORD = "throwaway"
TABLES = (
    "accounts_customuser",
    "catalog_outboxevent",
    "questionnaires_questionnairetype",
    "questionnaires_batterytype",
    "questionnaires_batterytypeitem",
)


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    info = subprocess.run(["docker", "info"], check=False, capture_output=True)  # noqa: S607
    return info.returncode == 0


pytestmark = pytest.mark.skipif(not docker_available(), reason="needs Docker")


def run(*argv: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=True, capture_output=True, text=True, **kwargs)  # noqa: S603


@pytest.fixture(scope="module")
def postgres():
    name = f"saas-schema-test-{uuid.uuid4().hex[:8]}"
    run(
        "docker", "run", "--rm", "-d", "--name", name,
        "--tmpfs", "/var/lib/postgresql/data",
        "-e", f"POSTGRES_PASSWORD={PASSWORD}",
        "-p", "127.0.0.1::5432", IMAGE,
    )  # fmt: skip
    try:
        port = run("docker", "port", name, "5432/tcp").stdout.splitlines()[0]
        port = port.rsplit(":", 1)[1]
        # Over TCP: the image's init-time server listens only on its socket, and
        # restarts once init is done.
        ready = ("docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-q")
        for _ in range(120):
            if subprocess.run(ready, check=False).returncode == 0:  # noqa: S603
                break
            time.sleep(0.5)
        psql = ("docker", "exec", name, "psql", "-U", "postgres", "-qc")
        run(*psql, "CREATE DATABASE baseline")
        # As the LXC deploy's databases are: text comes back as bytes unless the
        # client asks for UTF-8 (#37).
        run(*psql, "CREATE DATABASE alembic ENCODING 'SQL_ASCII' TEMPLATE template0")
        yield name, f"postgres://postgres:{PASSWORD}@127.0.0.1:{port}"
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)  # noqa: S603, S607


def env(url: str) -> dict:
    return {**os.environ, "SETTINGS": "dev", "DATABASE_URL": url}


def schema(container: str, database: str) -> list[str]:
    tables = [arg for table in TABLES for arg in ("-t", table)]
    pg_dump = ("docker", "exec", container, "pg_dump", "-U", "postgres", "-s")
    dump = run(*pg_dump, *tables, database)
    lines = (line.strip().rstrip(",") for line in dump.stdout.splitlines())
    return sorted(
        line
        for line in lines
        if line and not line.startswith(("--", "SET ", "SELECT ", "\\"))
    )


CLI = (sys.executable, "-m", "catalog")
ALEMBIC = (sys.executable, "-m", "alembic", "-c", "catalog/alembic.ini")


def test_baseline_is_the_schema_django_built(postgres):
    container, base = postgres
    run(*ALEMBIC, "upgrade", "0001", cwd=BACKEND, env=env(f"{base}/baseline"))
    assert schema(container, "baseline") == SNAPSHOT.read_text().splitlines()


def test_a_database_django_built_is_adopted(postgres):
    # What Django left: the baseline's tables, with no alembic_version.
    container, base = postgres
    psql = ("docker", "exec", container, "psql", "-U", "postgres", "-d", "baseline")
    run(*psql, "-qc", "DROP TABLE alembic_version")
    result = run(*CLI, "migrate", cwd=BACKEND, env=env(f"{base}/baseline"))
    assert "adopted" in result.stdout
    again = run(*CLI, "migrate", cwd=BACKEND, env=env(f"{base}/baseline"))
    assert "adopted" not in again.stdout


def test_models_match_the_migrations(postgres):
    # On a SQL_ASCII database, as the LXC deploy's are.
    _container, base = postgres
    on_alembic = {"cwd": BACKEND, "env": env(f"{base}/alembic")}
    run(*CLI, "migrate", **on_alembic)
    check = run(*ALEMBIC, "check", **on_alembic)
    assert "No new upgrade operations detected" in check.stdout + check.stderr


RACE = """
import json, threading
from catalog import peers, services
from catalog.db import session_factory
from catalog.models import QuestionnaireType, User

class Recorder:
    def __init__(self):
        self.events, self.lock = [], threading.Lock()
    def send_event(self, event):
        with self.lock:
            self.events.append(event)
    def retire(self, *args):
        pass

recorder = Recorder()
peers.set_instances_client(recorder)
with session_factory()() as session:
    user = User(email="race@example.com", password="x")
    session.add(user)
    session.commit()
    qtype = QuestionnaireType(owner_id=user.id, title="start")
    type_id = services.save_type(session, qtype, owner_id=user.id).id

def write(title, barrier):
    with session_factory()() as session:
        qtype = session.get(QuestionnaireType, type_id)
        qtype.title = title
        barrier.wait()
        services.save_type(session, qtype, owner_id=qtype.owner_id)

after_each_round = []
for round_ in range(20):
    barrier = threading.Barrier(2)
    threads = [
        threading.Thread(target=write, args=(f"{round_}-{side}", barrier))
        for side in "ab"
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    with session_factory()() as session:
        stored = session.get(QuestionnaireType, type_id)
        after_each_round.append([stored.version, stored.title])
print(json.dumps({
    "events": [[e["version"], e["data"]["title"]] for e in recorder.events],
    "after_each_round": after_each_round,
}))
"""


def test_record_change_orders_concurrent_writers(postgres):
    # Two writers of one type: versions must follow the order of the states they
    # carry, or `instances` would keep an older state as the newest (#13).
    _container, base = postgres
    environment = {**env(f"{base}/alembic"), "CACHE_ENABLED": "false"}
    result = run(sys.executable, "-c", RACE, cwd=BACKEND, env=environment)
    found = json.loads(result.stdout.strip().splitlines()[-1])
    events = sorted(found["events"])
    assert [version for version, _title in events] == list(range(1, 42))
    # After each round the stored row is exactly the newest event's state: the
    # write that committed last carries the higher version.
    newest_by_round = {}
    for version, title in events[1:]:
        newest_by_round[title.split("-")[0]] = [version, title]
    assert found["after_each_round"] == [newest_by_round[str(r)] for r in range(20)]
