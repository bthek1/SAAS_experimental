#!/usr/bin/env python3
"""Per-minute table for one k6 run, from Prometheus (#9, Phase 5).

    just k6-report <testid>

Reads loadtest/results/<testid>.meta.json (written by run.sh: the run's window
and its Prometheus), then prints a markdown table, one row per minute:
throughput and errors from k6, latency from k6 and from Django, and each
container's CPU as a share of its limit beside Postgres. The resource that
saturates first is the column that reaches 100 % first. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"
STEP = 60

DJANGO_LATENCY = "django_http_requests_latency_seconds_by_view_method_bucket"
CACHE_REQUESTS = "app_cache_requests_total"
CACHE_GROUPS = ("dashboard", "dashboard-scores", "pdf", "type-list")


def cpu_share(role: str) -> str:
    instance = f'instance="saas-{role}"'
    return (
        f"100 * sum(rate(container_cpu_usage_seconds_total{{{instance}}}[1m]))"
        f" / max(container_cpu_limit_cores{{{instance}}})"
    )


def cache_hit_ratio(group: str) -> str:
    hits = f'sum(rate({CACHE_REQUESTS}{{group="{group}", result="hit"}}[1m]))'
    reads = f'sum(rate({CACHE_REQUESTS}{{group="{group}", result=~"hit|miss"}}[1m]))'
    return f"100 * {hits} / {reads}"


def django_quantile(q: float) -> str:
    return f"1000 * histogram_quantile({q}, sum by (le) (rate({DJANGO_LATENCY}[1m])))"


def columns(testid: str) -> list[tuple[str, str, str]]:
    """(header, PromQL, format). Instant values at the end of each minute."""
    k6 = f'testid="{testid}"'
    reqs = f"sum(rate(k6_http_reqs_total{{{k6}}}[1m]))"
    failed = f"sum(rate(k6_http_reqs_total{{{k6}, expected_response='false'}}[1m]))"
    return [
        ("req/s", reqs, "{:.1f}"),
        ("failed %", f"100 * (({failed}) or vector(0)) / {reqs}", "{:.2f}"),
        (
            "dropped/min",
            f"sum(increase(k6_dropped_iterations_total{{{k6}}}[1m])) or vector(0)",
            "{:.0f}",
        ),
        (
            "k6 p95 worst group ms",
            f"1000 * max(max_over_time(k6_http_req_duration_p95{{{k6}}}[1m]))",
            "{:.0f}",
        ),
        ("django p95 ms", django_quantile(0.95), "{:.0f}"),
        ("django p99 ms", django_quantile(0.99), "{:.0f}"),
        *(
            (f"{role} cpu %", cpu_share(role), "{:.0f}")
            for role in ("app", "db", "cache", "loadgen", "monitor")
        ),
        *(
            (f"{group} hit %", cache_hit_ratio(group), "{:.0f}")
            for group in CACHE_GROUPS
        ),
        (
            # CONN_MAX_AGE is 0: one connection per request, so a sample is mostly 0.
            "pg conns (sampled)",
            'sum(pg_stat_activity_count{datname="appdb"})',
            "{:.0f}",
        ),
        (
            "pg commits/s",
            'sum(rate(pg_stat_database_xact_commit{datname="appdb"}[1m]))',
            "{:.0f}",
        ),
    ]


def query_range(prometheus: str, expr: str, start: float, end: float) -> dict:
    params = urllib.parse.urlencode(
        {"query": expr, "start": start, "end": end, "step": STEP}
    )
    url = f"{prometheus}/api/v1/query_range?{params}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Prometheus refused {expr!r}: {exc.read().decode()}")
    result = body["data"]["result"]
    return {float(t): float(v) for t, v in result[0]["values"]} if result else {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("testid")
    args = parser.parse_args()
    meta_path = RESULTS / f"{args.testid}.meta.json"
    if not meta_path.exists():
        sys.exit(f"no {meta_path}: run.sh writes it at the end of each run")
    meta = json.loads(meta_path.read_text())
    # The first full minute after the start, to the last one before the end.
    start = math.ceil(meta["start_ms"] / 1000 / STEP) * STEP + STEP
    end = math.floor(meta["end_ms"] / 1000 / STEP) * STEP
    cols = columns(args.testid)
    series = [query_range(meta["prometheus"], expr, start, end) for _, expr, _ in cols]

    print(  # noqa: T201
        f"**{args.testid}** ({meta['scenario']}, target {meta['target']}, "
        f"exit {meta['exit']})\n"
    )
    print("| min | " + " | ".join(h for h, _, _ in cols) + " |")  # noqa: T201
    print("|---" * (len(cols) + 1) + "|")  # noqa: T201
    for minute, t in enumerate(range(int(start), int(end) + 1, STEP), start=1):
        cells = []
        for (_, _, fmt), values in zip(cols, series, strict=True):
            value = values.get(float(t))
            ok = value is not None and math.isfinite(value)
            cells.append(fmt.format(value) if ok else "-")
        print(f"| {minute} | " + " | ".join(cells) + " |")  # noqa: T201


if __name__ == "__main__":
    main()
