"""Prometheus and Grafana config in infra/observability/ (#9)."""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OBS = REPO_ROOT / "infra" / "observability"
GRAFANA = OBS / "grafana"
PROMETHEUS_IMAGE = "prom/prometheus:v3.15.0"

pytestmark = pytest.mark.skipif(
    not OBS.is_dir(), reason="infra/observability not present"
)

requires_docker = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker CLI not installed"
)


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_dashboards", GRAFANA / "build_dashboards.py"
    )
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_dashboards_match_the_generator():
    rendered = load_builder().render()
    committed = {path.name for path in (GRAFANA / "dashboards").glob("*.json")}
    assert committed == set(rendered), "run build_dashboards.py"
    for name, text in rendered.items():
        assert (GRAFANA / "dashboards" / name).read_text() == text, (
            f"{name} is stale: python3 infra/observability/grafana/build_dashboards.py"
        )


def test_every_panel_uses_the_provisioned_datasource():
    provisioned = (
        GRAFANA / "provisioning" / "datasources" / "prometheus.yml"
    ).read_text()
    assert "uid: prometheus" in provisioned
    for path in (GRAFANA / "dashboards").glob("*.json"):
        dashboard = json.loads(path.read_text())
        for panel in dashboard["panels"]:
            uids = {panel["datasource"]["uid"]} | {
                t["datasource"]["uid"] for t in panel["targets"]
            }
            assert uids == {"prometheus"}, f"{path.name}: {panel['title']}"


def test_compose_mounts_this_folder():
    compose = (
        REPO_ROOT / "infra" / "docker" / "docker-compose.loadtest.yml"
    ).read_text()
    assert "../observability/prometheus:/etc/prometheus:ro" in compose
    assert (
        "../observability/grafana/dashboards:/var/lib/grafana/dashboards:ro" in compose
    )
    assert "--web.enable-remote-write-receiver" in compose


@requires_docker
@pytest.mark.slow
@pytest.mark.parametrize(
    "args",
    [
        ["check", "config", "/etc/prometheus/prometheus.yml"],
        ["check", "rules", "/etc/prometheus/rules.yml"],
    ],
    ids=["config", "rules"],
)
def test_promtool(args):
    cmd = [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "promtool",
        "-v",
        f"{OBS / 'prometheus'}:/etc/prometheus:ro",
        PROMETHEUS_IMAGE,
        *args,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    assert result.returncode == 0, result.stdout + result.stderr


def test_service_panels_read_both_frameworks():
    # instances exports django-prometheus names, catalog its own (#37). A panel that
    # read only one would show half the traffic.
    dashboard = (
        REPO_ROOT / "infra/observability/grafana/dashboards/django.json"
    ).read_text()
    for django_name, fastapi_name in [
        (
            "django_http_requests_total_by_view_transport_method_total",
            "http_requests_total",
        ),
        (
            "django_http_requests_latency_seconds_by_view_method_bucket",
            "http_request_duration_seconds_bucket",
        ),
        ("django_db_execute_total", "db_queries_total"),
        ("django_db_query_duration_seconds_bucket", "db_query_duration_seconds_bucket"),
    ]:
        assert django_name in dashboard
        assert fastapi_name in dashboard


def test_fastapi_latency_buckets_match_django_prometheus():
    # histogram_quantile over both families is only valid with the same bucket edges.
    from django_prometheus.conf import PROMETHEUS_LATENCY_BUCKETS

    from catalog.db import LATENCY_BUCKETS

    assert tuple(LATENCY_BUCKETS) == tuple(PROMETHEUS_LATENCY_BUCKETS)
