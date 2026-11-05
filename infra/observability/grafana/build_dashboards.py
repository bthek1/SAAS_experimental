"""Generate the Grafana dashboards in dashboards/ (#9). Standard library only.

    python3 infra/observability/grafana/build_dashboards.py

Edit this file, not the JSON: backend/tests/test_observability.py fails when the
committed JSON differs from what this writes.

k6 writes by remote write with K6_PROMETHEUS_RW_TREND_AS_NATIVE_HISTOGRAM, so a
trend such as http_req_duration arrives as a native histogram,
k6_http_req_duration_seconds, one series per `name` tag (endpoint group) and
status. Runs before #20 have k6_http_req_duration_{p50,p95,p99} instead, calculated
since the run began, so latency panels fall back to those for old runs.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dashboards"
DATASOURCE = {"type": "prometheus", "uid": "prometheus"}

K6 = 'testid=~"$testid", name=~"$name"'
SERVICE = 'service=~"$service"'
SERVICE_VIEW = f'{SERVICE}, view=~"$view"'
BY_SERVICE = "{{service}}"


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


def k6_latency(q: str) -> str:
    quantile = int(q[1:]) / 100
    histogram = f"rate(k6_http_req_duration_seconds{{{K6}}}[1m])"
    return (
        f"histogram_quantile({quantile}, sum by (name) ({histogram}))"
        f" or max by (name) (k6_http_req_duration_{q}{{{K6}}})"
    )


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
                    [(k6_latency(q), "{{name}}")],
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
    db_queries = f"sum by (service) ({rate('django_db_execute_total', SERVICE)})"
    requests = (
        "sum by (service) "
        f"({rate('django_http_requests_before_middlewares_total', SERVICE)})"
    )
    return dashboard(
        "django",
        "Django",
        [
            panel(
                "Requests by service",
                [(f"sum by (service) ({rate(REQUESTS, SERVICE)})", BY_SERVICE)],
                unit="reqps",
            ),
            panel(
                "Latency p95 by service",
                [(quantile(0.95, LATENCY, ", service", SERVICE), BY_SERVICE)],
                unit="s",
            ),
            panel(
                "Requests by view",
                [
                    (
                        f"sum by (service, view) ({rate(REQUESTS, SERVICE_VIEW)})",
                        "{{service}} {{view}}",
                    )
                ],
                unit="reqps",
            ),
            panel(
                "Responses by status",
                [
                    (
                        f"sum by (service, status) ({rate(STATUSES, SERVICE)})",
                        "{{service}} {{status}}",
                    )
                ],
                unit="reqps",
            ),
            *(
                panel(
                    f"Latency p{round(q * 100)} by view",
                    [
                        (
                            quantile(q, LATENCY, ", service, view", SERVICE_VIEW),
                            "{{service}} {{view}}",
                        )
                    ],
                    unit="s",
                    width=8,
                )
                for q in (0.5, 0.95, 0.99)
            ),
            panel(
                "DB queries per request",
                [(f"{db_queries} / {requests}", BY_SERVICE)],
                width=8,
            ),
            panel("DB query rate", [(db_queries, BY_SERVICE)], width=8),
            panel(
                "Outbox: events waiting for instances",
                [("max(app_outbox_pending_events)", "pending")],
                width=8,
            ),
            panel(
                "Outbox: oldest waiting event",
                [("max(app_outbox_oldest_pending_seconds)", "oldest")],
                unit="s",
                width=8,
            ),
            panel(
                "Read-throughs and refused deletes",
                [
                    (
                        f"sum by (result) ({rate('app_ref_read_through_total')})",
                        "read-through {{result}}",
                    ),
                    (
                        f"sum({rate('app_retire_failures_total')})",
                        "deletes refused",
                    ),
                ],
                unit="reqps",
                width=8,
            ),
            panel(
                "DB query latency",
                [
                    (
                        quantile(0.95, DB_LATENCY, ", service", SERVICE),
                        "{{service}} p95",
                    ),
                    (
                        quantile(0.5, DB_LATENCY, ", service", SERVICE),
                        "{{service}} p50",
                    ),
                ],
                unit="s",
                width=8,
            ),
        ],
        [
            query_var("service", f"label_values({REQUESTS}, service)", multi=True),
            query_var(
                "view",
                f"label_values({REQUESTS}{{{SERVICE}}}, view)",
                multi=True,
            ),
        ],
        "django-prometheus on catalog and instances (/metrics, scraped directly).",
    )


GATEWAY = 'instance="saas-gateway"'
GATEWAY_ETH0 = f'{GATEWAY}, device="eth0"'
NET_RX_BYTES = "node_network_receive_bytes_total"
NET_TX_BYTES = "node_network_transmit_bytes_total"
# /internal/ goes straight from service to service, never through the gateway.
THROUGH_GATEWAY = 'view!~".*internal_views.*"'


def gateway_dashboard():
    """saas-gateway, from what surrounds it: nginx has no metrics or access log.

    So there is no per-route status or upstream latency here. k6's numbers exist only
    during a run, and the gap between sent and arrived includes traffic not from k6.
    """
    return dashboard(
        "gateway",
        "Gateway",
        [
            panel(
                "k6 sent, and what arrived at each service",
                [
                    (f"sum({rate(REQS)})", "k6 sent"),
                    (
                        f"sum by (service) ({rate(REQUESTS, THROUGH_GATEWAY)})",
                        "{{service}} arrived",
                    ),
                ],
                unit="reqps",
            ),
            panel(
                "502 and 504 seen by k6 (service down or too slow)",
                [
                    (
                        f"""sum({rate(REQS, f'status="{status}"')}) or vector(0)""",
                        status,
                    )
                    for status in ("502", "504")
                ],
                unit="reqps",
            ),
            panel(
                "CPU used (cores)",
                [
                    (
                        f"sum({rate('container_cpu_usage_seconds_total', GATEWAY)})",
                        "used",
                    ),
                    (f"max(container_cpu_limit_cores{{{GATEWAY}}})", "limit"),
                ],
                width=8,
            ),
            panel(
                "Memory working set",
                [
                    (f"max(container_memory_working_set_bytes{{{GATEWAY}}})", "used"),
                    (f"max(container_memory_limit_bytes{{{GATEWAY}}})", "limit"),
                ],
                unit="bytes",
                width=8,
            ),
            panel(
                "TCP connections",
                [
                    (f"max(node_netstat_Tcp_CurrEstab{{{GATEWAY}}})", "established"),
                    (f"max(node_sockstat_TCP_tw{{{GATEWAY}}})", "time_wait"),
                ],
                width=8,
            ),
            panel(
                "Network",
                [
                    (f"sum({rate(NET_RX_BYTES, GATEWAY_ETH0)})", "received"),
                    (f"sum({rate(NET_TX_BYTES, GATEWAY_ETH0)})", "sent"),
                ],
                unit="Bps",
                width=24,
            ),
        ],
        [],
        "nginx in front of both services, on saas-gateway (the LXC deploy only).",
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


# The services' databases on saas-db (#13). appdb is the monolith's, from before the split.
APPDB = 'datname=~"catalogdb|instancesdb"'


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
                "Transactions (both services)",
                [
                    (appdb_rate("xact_commit"), "commits/s"),
                    (appdb_rate("xact_rollback"), "rollbacks/s"),
                ],
            ),
            panel(
                "Cache hit ratio (both services)",
                [(HIT_RATIO, "hit ratio")],
                unit="percentunit",
            ),
            panel(
                "Rows (both services)",
                [
                    (appdb_rate(f"tup_{kind}"), kind)
                    for kind in ("fetched", "returned", "inserted", "updated")
                ],
            ),
        ],
        [],
        "postgres_exporter on saas-db (the LXC deploy only).",
    )


CACHE_REQUESTS = "app_cache_requests_total"


def redis_dashboard():
    # From the app's own counter. Redis's keyspace_hits also counts generation
    # lookups, which nearly always hit.
    hits = f'sum by (group) (rate({CACHE_REQUESTS}{{result="hit"}}[1m]))'
    reads = f'sum by (group) (rate({CACHE_REQUESTS}{{result=~"hit|miss"}}[1m]))'
    return dashboard(
        "redis",
        "Redis cache",
        [
            panel(
                "Hit ratio by group",
                [(f"{hits} / {reads}", "{{group}}")],
                unit="percentunit",
            ),
            panel(
                "Cached reads and errors",
                [
                    (
                        f"sum by (group, result) (rate({CACHE_REQUESTS}[1m]))",
                        "{{group}} {{result}}",
                    )
                ],
            ),
            panel(
                "Memory",
                [
                    ("max(redis_memory_used_bytes)", "used"),
                    ("max(redis_memory_max_bytes)", "maxmemory"),
                ],
                unit="bytes",
            ),
            panel(
                "Evicted and expired keys",
                [
                    ("sum(rate(redis_evicted_keys_total[1m]))", "evicted/s"),
                    ("sum(rate(redis_expired_keys_total[1m]))", "expired/s"),
                ],
            ),
            panel(
                "Commands",
                [("sum(rate(redis_commands_processed_total[1m]))", "commands/s")],
            ),
            panel("Connections", [("max(redis_connected_clients)", "clients")]),
        ],
        [],
        "The API's cache (#11): redis_exporter, plus the app's own hit and miss counter.",
    )


DASHBOARDS = {
    "k6.json": k6_dashboard,
    "django.json": django_dashboard,
    "gateway.json": gateway_dashboard,
    "containers.json": containers_dashboard,
    "postgres.json": postgres_dashboard,
    "redis.json": redis_dashboard,
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
