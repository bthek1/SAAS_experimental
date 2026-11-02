"""Generate the Grafana dashboards in dashboards/ (#9). Standard library only.

    python3 infra/observability/grafana/build_dashboards.py

Edit this file, not the JSON: backend/tests/test_observability.py fails when the
committed JSON differs from what this writes.

k6 writes by remote write with K6_PROMETHEUS_RW_TREND_STATS, so a trend such
as http_req_duration arrives as k6_http_req_duration_{p50,p95,p99,avg,max} in
seconds, one series per `name` tag (endpoint group) and status.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dashboards"
DATASOURCE = {"type": "prometheus", "uid": "prometheus"}

K6 = 'testid=~"$testid", name=~"$name"'
DJANGO_VIEW = 'view=~"$view"'


def target(expr: str, legend: str, ref: str = "A") -> dict:
    return {
        "datasource": DATASOURCE,
        "expr": expr,
        "legendFormat": legend,
        "refId": ref,
    }


def panel(title, targets, *, unit="short", kind="timeseries", width=12, height=8):
    return {
        "type": kind,
        "title": title,
        "datasource": DATASOURCE,
        "targets": [
            target(expr, legend, chr(ord("A") + i))
            for i, (expr, legend) in enumerate(targets)
        ],
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "right"}}
        if kind == "timeseries"
        else {"reduceOptions": {"calcs": ["lastNotNull"]}},
        "gridPos": {"w": width, "h": height},
    }


def stat(title, expr, unit="short"):
    return panel(title, [(expr, "")], unit=unit, kind="stat", width=6, height=4)


def query_var(name, query, *, multi=False, label=None):
    return {
        "name": name,
        "label": label or name,
        "type": "query",
        "datasource": DATASOURCE,
        "query": {"query": query, "refId": name},
        "definition": query,
        "refresh": 2,
        "sort": 2 if name == "testid" else 1,
        "multi": multi,
        "includeAll": multi,
        "allValue": ".*" if multi else None,
        "current": {},
    }


def layout(panels):
    """Place panels left to right, wrapping at Grafana's 24 columns."""
    x = y = row_height = 0
    for i, p in enumerate(panels, start=1):
        grid = p["gridPos"]
        if x + grid["w"] > 24:
            x, y, row_height = 0, y + row_height, 0
        grid.update(x=x, y=y)
        p["id"] = i
        x += grid["w"]
        row_height = max(row_height, grid["h"])
    return panels


def dashboard(uid, title, panels, variables, description):
    return {
        "uid": uid,
        "title": title,
        "description": description,
        "tags": ["loadtest"],
        "editable": False,
        "schemaVersion": 41,
        "time": {"from": "now-30m", "to": "now"},
        "refresh": "10s",
        "templating": {"list": variables},
        "panels": layout(panels),
    }


def series(metric: str, selector: str = "") -> str:
    return f"{metric}{{{selector}}}" if selector else metric


def rate(metric: str, selector: str = "") -> str:
    return f"rate({series(metric, selector)}[$__rate_interval])"


def increase(metric: str, selector: str = "") -> str:
    return f"increase({series(metric, selector)}[$__range])"


TESTID = 'testid=~"$testid"'
FAILED = f"{K6}, expected_response='false'"
REQS = "k6_http_reqs_total"
DROPPED = "k6_dropped_iterations_total"


def k6_dashboard():
    return dashboard(
        "k6",
        "k6",
        [
            stat("Requests", f"sum({increase(REQS, K6)})"),
            # No failed series at all is 0 %, not "No data".
            stat(
                "Failed requests",
                f"(sum({increase(REQS, FAILED)}) or vector(0))"
                f" / sum({increase(REQS, K6)})",
                "percentunit",
            ),
            stat("Peak VUs", f"max(max_over_time(k6_vus{{{TESTID}}}[$__range]))"),
            stat(
                "Dropped iterations",
                f"sum({increase(DROPPED, TESTID)}) or vector(0)",
            ),
            panel(
                "Request rate",
                [
                    (f"sum({rate(REQS, K6)})", "all"),
                    (f"sum by (name) ({rate(REQS, K6)})", "{{name}}"),
                ],
                unit="reqps",
            ),
            panel(
                "VUs and iterations",
                [
                    (f"sum(k6_vus{{{TESTID}}})", "VUs"),
                    (f"sum({rate('k6_iterations_total', TESTID)})", "iterations/s"),
                ],
            ),
            *(
                panel(
                    f"Latency {q} by endpoint group",
                    [(f"max by (name) (k6_http_req_duration_{q}{{{K6}}})", "{{name}}")],
                    unit="s",
                    width=8,
                )
                for q in ("p50", "p95", "p99")
            ),
            panel(
                "Failed requests by endpoint group",
                [(f"sum by (name) ({rate(REQS, FAILED)})", "{{name}}")],
                unit="reqps",
            ),
            panel(
                "Responses by status",
                [(f"sum by (status) ({rate(REQS, K6)})", "{{status}}")],
                unit="reqps",
            ),
            panel(
                "Check pass rate",
                [(f"min by (check) (k6_checks_rate{{{TESTID}}})", "{{check}}")],
                unit="percentunit",
            ),
            panel(
                "Dropped iterations",
                [
                    (
                        f"sum({rate(DROPPED, TESTID)}) or vector(0)",
                        "dropped/s",
                    )
                ],
            ),
        ],
        [
            query_var("testid", f"label_values({REQS}, testid)"),
            query_var(
                "name",
                f"label_values({REQS}{{{TESTID}}}, name)",
                multi=True,
                label="endpoint group",
            ),
        ],
        "k6 runs from loadtest/run.sh (`just k6 <scenario>`), one testid per run.",
    )


LATENCY = "django_http_requests_latency_seconds_by_view_method_bucket"
REQUESTS = "django_http_requests_total_by_view_transport_method_total"
DB_LATENCY = "django_db_query_duration_seconds_bucket"
STATUSES = "django_http_responses_total_by_status_total"


def quantile(q: float, bucket: str, by: str = "", selector: str = "") -> str:
    return f"histogram_quantile({q}, sum by (le{by}) ({rate(bucket, selector)}))"


def django_dashboard():
    db_queries = f"sum({rate('django_db_execute_total')})"
    requests = f"sum({rate('django_http_requests_before_middlewares_total')})"
    return dashboard(
        "django",
        "Django",
        [
            panel(
                "Requests by view",
                [(f"sum by (view) ({rate(REQUESTS, DJANGO_VIEW)})", "{{view}}")],
                unit="reqps",
            ),
            panel(
                "Responses by status",
                [
                    (
                        f"sum by (status) ({rate(STATUSES)})",
                        "{{status}}",
                    )
                ],
                unit="reqps",
            ),
            *(
                panel(
                    f"Latency p{round(q * 100)} by view",
                    [(quantile(q, LATENCY, ", view", DJANGO_VIEW), "{{view}}")],
                    unit="s",
                    width=8,
                )
                for q in (0.5, 0.95, 0.99)
            ),
            panel(
                "DB queries per request",
                [(f"{db_queries} / {requests}", "queries/request")],
                width=8,
            ),
            panel("DB query rate", [(db_queries, "queries/s")], width=8),
            panel(
                "DB query latency",
                [
                    (quantile(0.95, DB_LATENCY), "p95"),
                    (quantile(0.5, DB_LATENCY), "p50"),
                ],
                unit="s",
                width=8,
            ),
        ],
        [query_var("view", f"label_values({REQUESTS}, view)", multi=True)],
        "django-prometheus on the backend (/metrics, scraped by Prometheus).",
    )


INSTANCE = 'instance=~"$instance"'
ETH0 = f'{INSTANCE}, device="eth0"'
CPU_USED = f"sum by (instance) ({rate('container_cpu_usage_seconds_total', INSTANCE)})"
CPU_LIMIT = f"max by (instance) (container_cpu_limit_cores{{{INSTANCE}}})"
MEM_USED = f"max by (instance) (container_memory_usage_bytes{{{INSTANCE}}})"
# What the limit bites: usage minus inactive page cache (cAdvisor's working set).
MEM_WORKING = f"max by (instance) (container_memory_working_set_bytes{{{INSTANCE}}})"
MEM_LIMIT = f"max by (instance) (container_memory_limit_bytes{{{INSTANCE}}})"
NET_RX = f"sum by (instance) ({rate('node_network_receive_bytes_total', ETH0)})"
NET_TX = f"sum by (instance) ({rate('node_network_transmit_bytes_total', ETH0)})"
BY_INSTANCE = "{{instance}}"


def containers_dashboard():
    """The LXC deploy's containers, each against its own limits.

    From each container's cgroup (infra/ansible/roles/common: container-metrics),
    not node_exporter's CPU metrics, which inside an LXC count the host's work
    on the container's cores.
    """
    return dashboard(
        "containers",
        "Containers",
        [
            panel(
                "CPU used (cores)",
                [(CPU_USED, BY_INSTANCE), (CPU_LIMIT, "{{instance}} limit")],
            ),
            panel(
                "CPU used, share of limit",
                [(f"{CPU_USED} / {CPU_LIMIT}", BY_INSTANCE)],
                unit="percentunit",
            ),
            panel(
                "Memory working set, share of limit",
                [(f"{MEM_WORKING} / {MEM_LIMIT}", BY_INSTANCE)],
                unit="percentunit",
            ),
            panel(
                "Memory: working set and total (incl. page cache)",
                [
                    (MEM_WORKING, "{{instance}} working set"),
                    (MEM_USED, "{{instance}} total"),
                ],
                unit="bytes",
            ),
            panel("Network received", [(NET_RX, BY_INSTANCE)], unit="Bps"),
            panel("Network sent", [(NET_TX, BY_INSTANCE)], unit="Bps"),
        ],
        [
            query_var(
                "instance",
                "label_values(container_cpu_limit_cores, instance)",
                multi=True,
            )
        ],
        "LXC containers on Proxmox: cgroup CPU and memory against each limit.",
    )


APPDB = 'datname="appdb"'


def appdb_rate(stat: str) -> str:
    return f"sum({rate(f'pg_stat_database_{stat}', APPDB)})"


HIT_RATIO = (
    f"{appdb_rate('blks_hit')} / ({appdb_rate('blks_hit')} + {appdb_rate('blks_read')})"
)


def postgres_dashboard():
    return dashboard(
        "postgres",
        "Postgres",
        [
            panel(
                "Connections by state",
                [
                    ("sum by (state) (pg_stat_activity_count)", "{{state}}"),
                    ("max(pg_settings_max_connections)", "max_connections"),
                ],
            ),
            panel(
                "Transactions (appdb)",
                [
                    (appdb_rate("xact_commit"), "commits/s"),
                    (appdb_rate("xact_rollback"), "rollbacks/s"),
                ],
            ),
            panel(
                "Cache hit ratio (appdb)",
                [(HIT_RATIO, "hit ratio")],
                unit="percentunit",
            ),
            panel(
                "Rows (appdb)",
                [
                    (appdb_rate(f"tup_{kind}"), kind)
                    for kind in ("fetched", "returned", "inserted", "updated")
                ],
            ),
        ],
        [],
        "postgres_exporter on saas-db (the LXC deploy only).",
    )


DASHBOARDS = {
    "k6.json": k6_dashboard,
    "django.json": django_dashboard,
    "containers.json": containers_dashboard,
    "postgres.json": postgres_dashboard,
}


def render() -> dict[str, str]:
    return {
        name: json.dumps(build(), indent=2, sort_keys=True) + "\n"
        for name, build in DASHBOARDS.items()
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, text in render().items():
        (OUT / name).write_text(text)
        print(f"wrote {OUT / name}")  # noqa: T201


if __name__ == "__main__":
    main()
