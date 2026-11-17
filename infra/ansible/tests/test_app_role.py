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


# What runs on every app container, what runs on catalog's alone (main.yml includes
# catalog.yml for it, and only it gets the relay unit), and instances' seeding.
SHARED = ("tasks/main.yml",)
UNIT = "templates/saas-app.service.j2"
CATALOG_ONLY = ("tasks/catalog.yml", "templates/saas-relay.service.j2")
INSTANCES_ONLY = ("tasks/seed_instances.yml",)
GROUP_VARS = ROLE.parents[1] / "group_vars"


def unit_commands(service: str) -> set[str]:
    """The unit template's branch for this service: Kestrel for instances, else gunicorn."""
    unit = (ROLE / UNIT).read_text()
    dotnet, rest = unit.split("{% else %}\nWorkingDirectory", 1)
    branch = dotnet if service == "instances" else rest
    return set(re.findall(r"app_cmd\.(\w+)", branch))


def test_the_commands_cover_every_file_that_runs_one():
    sources = [*(ROLE / "tasks").glob("*.yml"), *(ROLE / "templates").glob("*.j2")]
    users = {str(p.relative_to(ROLE)) for p in sources if "app_cmd." in p.read_text()}
    assert users == {*SHARED, UNIT, *CATALOG_ONLY, *INSTANCES_ONLY}


@pytest.mark.parametrize(
    ("service", "files"),
    [
        ("catalog", SHARED + CATALOG_ONLY),
        ("instances", SHARED + INSTANCES_ONLY),
    ],
)
def test_every_command_the_role_runs_is_defined(service, files):
    defined = set(DEFAULTS["app_commands"][service])
    assert commands_in(*files) <= defined
    assert unit_commands(service) <= defined


def test_only_catalog_gets_python():
    # instances is .NET (#45): no source sync, uv or Django left on its container.
    main = (ROLE / "tasks" / "main.yml").read_text()
    assert "include_tasks: python.yml" in main
    assert "when: app_service == 'catalog'\n  ansible.builtin.include_tasks: python.yml" in main
    assert set(DEFAULTS["app_commands"]) == {"catalog", "instances"}
    assert "instances_impl" not in (GROUP_VARS / "instances.yml").read_text()


def test_the_dotnet_runtime_is_pinned_by_version_and_sha256():
    pinned = yaml.safe_load((GROUP_VARS / "all.yml").read_text())
    assert re.fullmatch(r"\d+\.\d+\.\d+", pinned["dotnet_runtime_version"])
    assert re.fullmatch(r"[0-9a-f]{64}", pinned["dotnet_runtime_sha256"])
    assert "{{ dotnet_runtime_version }}" in pinned["dotnet_runtime_url"]


def test_the_relay_gets_its_own_metrics_directory():
    # EnvironmentFile= overrides Environment=, so the directory is set in the command,
    # where the env file cannot reach it. gunicorn's on_starting empties the service's.
    unit = (ROLE / "templates" / "saas-relay.service.j2").read_text()
    exec_start = next(
        line for line in unit.splitlines() if line.startswith("ExecStart=")
    )
    assert "/usr/bin/env PROMETHEUS_MULTIPROC_DIR=/run/saas-relay/" in exec_start
    assert "Environment=PROMETHEUS_MULTIPROC_DIR" not in unit


def test_both_services_read_the_loadtest_profile_from_settings():
    # catalog (FastAPI) and instances (.NET) both pick their profile from SETTINGS.
    shared = DEFAULTS["app_env_shared"]
    assert shared["SETTINGS"] == "loadtest"
    assert "DJANGO_SETTINGS_MODULE" not in shared
