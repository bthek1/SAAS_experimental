import pytest
from sqlalchemy import func, select

from catalog_fastapi import __main__ as cli
from catalog_fastapi.auth import check_password
from catalog_fastapi.models import BatteryTypeItem, OutboxEvent, QuestionnaireType, User
from catalog_fastapi.peers import PeerUnavailable
from catalog_fastapi.services import save_type
from catalog_fastapi.settings import get_settings


@pytest.fixture
def debug(monkeypatch):
    settings = get_settings().model_copy(update={"debug": True})
    monkeypatch.setattr(cli, "get_settings", lambda: settings)


def test_relay_once_delivers_pending(session, user, instances, capsys):
    instances.fail_events = PeerUnavailable("down")
    save_type(session, QuestionnaireType(owner_id=user.id, title="T"), owner_id=user.id)
    instances.fail_events = None
    cli.main(["relay-outbox", "--once"])
    assert "delivered: 1, pending: 0" in capsys.readouterr().out
    assert len(instances.events) == 1


def test_seed_refuses_outside_debug_and_loadtest():
    with pytest.raises(SystemExit):
        cli.main(["seed-loadtest", "--owners", "1", "--password", "x"])


def test_seed_needs_a_password(debug, monkeypatch):
    monkeypatch.delenv("LOADTEST_OWNER_PASSWORD", raising=False)
    with pytest.raises(SystemExit):
        cli.main(["seed-loadtest", "--owners", "1", "--password", ""])


def test_seed_is_idempotent(debug, session, instances, capsys):
    cli.main(["seed-loadtest", "--owners", "2", "--password", "pw-123456"])
    cli.main(["seed-loadtest", "--owners", "3", "--password", "pw-123456"])
    out = capsys.readouterr().out
    assert "owners: 2 created, 0 already there" in out
    assert "owners: 1 created, 2 already there" in out
    owner = session.scalars(
        select(User).filter_by(email="loadtest-0@example.com")
    ).one()
    assert check_password("pw-123456", owner.password)
    assert session.scalar(select(func.count()).select_from(QuestionnaireType)) == 9
    assert session.scalar(select(func.count()).select_from(BatteryTypeItem)) == 6
    # Three questionnaire types and one battery type per owner.
    assert len(instances.events) == 12


def test_create_superuser(session, monkeypatch, capsys):
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "admin-pass-1")
    cli.main(["create-superuser"])
    assert "superuser created" in capsys.readouterr().out
    admin = session.scalars(select(User).filter_by(email="admin@example.com")).one()
    assert (admin.is_staff, admin.is_superuser, admin.is_active) == (True, True, True)
    with pytest.raises(SystemExit):
        cli.main(["create-superuser"])


def test_outbox_counts(session, user):
    save_type(session, QuestionnaireType(owner_id=user.id, title="T"), owner_id=user.id)
    assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1


def test_reset_db_refuses_outside_debug_and_loadtest():
    with pytest.raises(SystemExit):
        cli.main(["reset-db"])


def test_reset_db_empties_the_tables(debug, session, user, capsys):
    save_type(session, QuestionnaireType(owner_id=user.id, title="T"), owner_id=user.id)
    cli.main(["reset-db"])
    assert "emptied" in capsys.readouterr().out
    session.expire_all()
    for model in (User, QuestionnaireType, OutboxEvent):
        assert session.scalar(select(func.count()).select_from(model)) == 0


def test_clear_cache(cache_on, monkeypatch, capsys):
    cache_on.data["x"] = b"1"
    monkeypatch.setattr(cache_on, "flushdb", cache_on.data.clear, raising=False)
    cli.main(["clear-cache"])
    assert cache_on.data == {}
    assert "cleared" in capsys.readouterr().out


def test_importing_creates_the_metrics_directory(tmp_path):
    import subprocess
    import sys

    directory = tmp_path / "multiproc" / "relay"
    subprocess.run(
        [sys.executable, "-c", "import catalog_fastapi.db"],
        env={"PROMETHEUS_MULTIPROC_DIR": str(directory), "SETTINGS": "test"},
        check=True,
    )
    assert directory.is_dir()
