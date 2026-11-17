"""gunicorn's multiprocess metrics setup (#9), for catalog (#13, #45)."""

import re
from pathlib import Path
from types import SimpleNamespace

from common import gunicorn_conf

BACKEND = Path(__file__).resolve().parent.parent


def test_catalog_uses_the_shared_config() -> None:
    """gunicorn reads this file from the working directory, so it has to exist.

    instances runs on Kestrel since #44: tests/test_kestrel_keepalive.py."""
    config = (BACKEND / "catalog" / "gunicorn.conf.py").read_text()
    assert "from common.gunicorn_conf import *" in config


def test_keepalive_outlasts_the_gateways() -> None:
    """Otherwise gunicorn can close a connection as nginx reuses it: a 502 (#24)."""
    nginx = (BACKEND.parent / "infra" / "gateway" / "nginx.conf").read_text()
    timeouts = re.findall(r"keepalive_timeout (\d+)s;", nginx)

    assert timeouts
    assert all(gunicorn_conf.keepalive > int(timeout) for timeout in timeouts)


def test_on_starting_empties_the_metrics_directory(tmp_path, monkeypatch) -> None:
    directory = tmp_path / "metrics"
    directory.mkdir()
    (directory / "counter_123.db").write_text("from the last run")
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(directory))

    gunicorn_conf.on_starting(None)

    assert directory.is_dir()
    assert list(directory.iterdir()) == []


def test_on_starting_creates_the_metrics_directory(tmp_path, monkeypatch) -> None:
    directory = tmp_path / "a" / "metrics"
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(directory))

    gunicorn_conf.on_starting(None)

    assert directory.is_dir()


def test_on_starting_touches_nothing_without_the_setting(monkeypatch, mocker) -> None:
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    rmtree = mocker.patch("common.gunicorn_conf.shutil.rmtree")

    gunicorn_conf.on_starting(None)

    rmtree.assert_not_called()


def test_child_exit_marks_the_worker_dead(tmp_path, monkeypatch, mocker) -> None:
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    mark = mocker.patch("prometheus_client.multiprocess.mark_process_dead")

    gunicorn_conf.child_exit(None, SimpleNamespace(pid=123))

    mark.assert_called_once_with(123)


def test_child_exit_does_nothing_without_the_setting(monkeypatch, mocker) -> None:
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    mark = mocker.patch("prometheus_client.multiprocess.mark_process_dead")

    gunicorn_conf.child_exit(None, SimpleNamespace(pid=123))

    mark.assert_not_called()
