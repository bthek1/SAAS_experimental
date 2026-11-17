"""Prometheus and Grafana config in infra/observability/ (#9)."""

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OBS = REPO_ROOT / "infra" / "observability"
GRAFANA = OBS / "grafana"
PROMETHEUS_IMAGE = "prom/prometheus:v3.15.0"
# django-prometheus's PROMETHEUS_LATENCY_BUCKETS, frozen when #45 removed the last
# service that ran it. Runs recorded before then carry these edges.
DJANGO_PROMETHEUS_BUCKETS = (
    0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0,
    2.5, 5.0, 7.5, 10.0, 25.0, 50.0, 75.0, float("inf"),
)  # fmt: skip

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
    # Django's instances exported django-prometheus names until #44, catalog and .NET
    # their own (#37); panels keep both, so earlier runs still show. A panel that
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
    from catalog.db import LATENCY_BUCKETS

    assert tuple(LATENCY_BUCKETS) == DJANGO_PROMETHEUS_BUCKETS


def test_dotnet_instances_emits_catalogs_names_and_buckets():
    # instances on .NET (#44) emits the family catalog does, so the panels and
    # `just k6-report` read it with no query of its own.
    source = (
        REPO_ROOT / "backend/instances_NET/src/Instances.Api/Http/RequestMetrics.cs"
    ).read_text()

    edges = re.search(r"LatencyBuckets =\s*\[([^\]]+)\]", source)[1]
    buckets = tuple(float(edge) for edge in edges.split(","))
    assert (*buckets, float("inf")) == DJANGO_PROMETHEUS_BUCKETS
    assert '"http_requests_total"' in source
    assert '"view", "method", "status"' in source
    assert '"http_request_duration_seconds"' in source
    assert '"db_queries_total"' in source
    assert '"db_query_duration_seconds"' in source
