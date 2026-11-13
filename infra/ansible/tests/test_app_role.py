"""The app role's commands and units, checked without a container (#37, #38)."""

import re
from pathlib import Path

import pytest
import yaml

ROLE = Path(__file__).resolve().parents[1] / "roles" / "app"
DEFAULTS = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text())


def commands_in(*names: str) -> set[str]:
    return {
        command
        for name in names
        for command in re.findall(r"app_cmd\.(\w+)", (ROLE / name).read_text())
    }


# What runs on every app container, and what runs on catalog's alone (main.yml
# includes catalog.yml for it, and only it gets the relay unit).
SHARED = ("tasks/main.yml", "templates/saas-app.service.j2")
CATALOG_ONLY = ("tasks/catalog.yml", "templates/saas-relay.service.j2")


def test_the_commands_cover_every_file_that_runs_one():
    sources = [*(ROLE / "tasks").glob("*.yml"), *(ROLE / "templates").glob("*.j2")]
    users = {str(p.relative_to(ROLE)) for p in sources if "app_cmd." in p.read_text()}
    assert users == {*SHARED, *CATALOG_ONLY}


@pytest.mark.parametrize(
    ("service", "files"),
    [("catalog", SHARED + CATALOG_ONLY), ("instances", SHARED)],
)
def test_every_command_the_role_runs_is_defined(service, files):
    assert commands_in(*files) <= set(DEFAULTS["app_commands"][service])


def test_the_relay_gets_its_own_metrics_directory():
    # EnvironmentFile= overrides Environment=, so the directory is set in the command,
    # where the env file cannot reach it. gunicorn's on_starting empties the service's.
    unit = (ROLE / "templates" / "saas-relay.service.j2").read_text()
    exec_start = next(
        line for line in unit.splitlines() if line.startswith("ExecStart=")
    )
    assert "/usr/bin/env PROMETHEUS_MULTIPROC_DIR=/run/saas-relay/" in exec_start
    assert "Environment=PROMETHEUS_MULTIPROC_DIR" not in unit


def test_both_settings_profiles_are_named():
    # instances (Django) reads DJANGO_SETTINGS_MODULE, catalog (FastAPI) reads SETTINGS.
    shared = DEFAULTS["app_env_shared"]
    assert shared["DJANGO_SETTINGS_MODULE"] == "core.settings.loadtest"
    assert shared["SETTINGS"] == "loadtest"
