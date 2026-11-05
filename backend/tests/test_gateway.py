"""The gateway's route table (#13). nginx.conf is generated from it."""

import importlib.util
import json
from pathlib import Path

import pytest

GATEWAY = Path(__file__).resolve().parents[2] / "infra" / "gateway"
TABLE = json.loads((GATEWAY / "routes.json").read_text())

# Every public path the API has (README), and the service that owns it.
PUBLIC = {
    "/api/token/": "catalog",
    "/api/token/refresh/": "catalog",
    "/api/accounts/register/": "catalog",
    "/api/accounts/me/": "catalog",
    "/api/health/": "catalog",
    "/api/tasks/trigger/": "catalog",
    "/api/questionnaire-types/": "catalog",
    "/api/battery-types/": "catalog",
    "/admin/": "catalog",
    "/api/questionnaires/": "instances",
    "/api/questionnaires/by-token/abc/submit/": "instances",
    "/api/batteries/": "instances",
    "/api/dashboard/": "instances",
    "/api/dashboard/scores/": "instances",
    "/instances-admin/": "instances",
}


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, GATEWAY / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_public_route_has_one_owner():
    prefixes = [route["prefix"] for route in TABLE["routes"]]
    assert len(prefixes) == len(set(prefixes))
    assert {route["service"] for route in TABLE["routes"]} == set(TABLE["services"])
    for prefix in prefixes:
        overlapping = [p for p in prefixes if p != prefix and p.startswith(prefix)]
        assert not overlapping, f"{prefix} also matches {overlapping}"
    router = load("dev_router")
    for path, owner in PUBLIC.items():
        assert router.service_for(path) == owner, path


@pytest.mark.parametrize(
    "path",
    ["/internal/events/", "/internal/health/", "/metrics", "/", "/api/", "/api/other/"],
)
def test_internal_and_metrics_are_not_routed(path):
    assert load("dev_router").service_for(path) is None


def test_nginx_has_no_private_location():
    conf = (GATEWAY / "nginx.conf").read_text()
    assert "/internal" not in conf
    assert "/metrics" not in conf
    assert "location / {" in conf
    assert "return 404" in conf


def test_nginx_conf_is_not_stale():
    assert (GATEWAY / "nginx.conf").read_text() == load("build_nginx").render(TABLE)


def test_a_stopped_service_fails_fast_and_a_restart_is_found():
    conf = (GATEWAY / "nginx.conf").read_text()
    assert "proxy_connect_timeout 2s;" in conf
    assert "resolver 127.0.0.11" in conf
    assert "server catalog:8000 resolve;" in conf


@pytest.mark.parametrize("addresses", [None, {"catalog": "a:1", "instances": "b:1"}])
def test_every_upstream_states_its_idle_timeout(addresses):
    # The Docker and LXC configs alike: gunicorn's keepalive is checked against it (#24).
    build = load("build_nginx")
    conf = build.render(TABLE, addresses)

    assert conf.count("upstream ") == conf.count(
        f"keepalive_timeout {build.KEEPALIVE_TIMEOUT}s;"
    )


def test_fixed_addresses_need_no_docker_dns():
    addresses = {"catalog": "192.168.2.241:8000", "instances": "192.168.2.246:8000"}
    conf = load("build_nginx").render(TABLE, addresses)
    assert "resolver" not in conf
    assert "server 192.168.2.241:8000;" in conf
    assert "/internal" not in conf
