"""k6 never targets a public host (#9).

A load test pointed at someone else's site is a denial-of-service attack. The
k6 scripts refuse a non-private BASE_URL at runtime (loadtest/k6/lib/config.js);
this checks the files themselves: every URL in loadtest/ names a private host,
and every scenario goes through the lib that holds the runtime check.
"""

import ipaddress
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LOADTEST = REPO_ROOT / "loadtest"
SCENARIOS = LOADTEST / "k6" / "scenarios"
URL_HOST = re.compile(r"\b[a-z][a-z0-9+.-]*://([^/:\s'\"`?#]+)", re.IGNORECASE)
PRIVATE_SUFFIXES = (".lan", ".internal", ".local", ".localhost")

pytestmark = pytest.mark.skipif(not LOADTEST.is_dir(), reason="loadtest/ not present")


def is_private(host: str) -> bool:
    if host == "localhost" or host.endswith(PRIVATE_SUFFIXES):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_private
    except ValueError:
        return False


def loadtest_files() -> list[Path]:
    return [
        path
        for path in LOADTEST.rglob("*")
        if path.is_file() and "results" not in path.relative_to(LOADTEST).parts
    ]


def test_there_are_scenarios():
    assert sorted(path.stem for path in SCENARIOS.glob("*.js")) == [
        "load",
        "pdf",
        "respondent",
        "smoke",
        "soak",
        "stress",
    ]


def test_every_url_names_a_private_host():
    # A variable (`${monitor}`) is resolved at runtime and checked there; see
    # test_run_sh_refuses_public_container_addresses.
    public = [
        f"{path.relative_to(REPO_ROOT)}: {host}"
        for path in loadtest_files()
        for host in URL_HOST.findall(path.read_text(errors="ignore"))
        if not host.startswith(("$", "{")) and not is_private(host)
    ]
    assert not public, f"public hosts in load-test files: {public}"


def test_run_sh_refuses_public_container_addresses():
    # TARGET=lxc reads saas-loadgen's and saas-monitor's IPs from the Pulumi
    # stack; run.sh must refuse them unless private before any request.
    run_sh = (LOADTEST / "run.sh").read_text()
    lxc = run_sh[run_sh.index("run_lxc() {") :]
    assert 'for ip in "$loadgen" "$monitor"; do' in lxc
    assert "ipaddress.ip_address(sys.argv[1]).is_private" in lxc
    assert lxc.index("is_private") < lxc.index("k6 run")


@pytest.mark.parametrize(
    "scenario", sorted(SCENARIOS.glob("*.js")), ids=lambda path: path.stem
)
def test_every_scenario_loads_the_guarded_config(scenario):
    # lib/api.js imports lib/config.js, whose module code refuses a public BASE_URL.
    imports = re.findall(r"from '(\.\./lib/[^']+)'", scenario.read_text())
    assert {"../lib/api.js", "../lib/config.js"} & set(imports), scenario.name


def test_config_refuses_public_targets_before_any_request():
    config = (LOADTEST / "k6" / "lib" / "config.js").read_text()
    assert "export const BASE_URL = baseUrl();" in config
    assert "refusing to load-test it" in config
    assert "from './config.js'" in (LOADTEST / "k6" / "lib" / "api.js").read_text()


@pytest.mark.parametrize(
    ("host", "private"),
    [
        ("api.loadtest.internal", True),
        ("localhost", True),
        ("192.168.2.241", True),
        ("10.95.0.10", True),
        ("example.com", False),
        ("8.8.8.8", False),
    ],
)
def test_is_private(host, private):
    assert is_private(host) is private
