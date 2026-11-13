#!/usr/bin/env python3
"""Per-minute table for one k6 run, from Prometheus (#9, Phase 5).

    just k6-report <testid>

Reads loadtest/results/<testid>.meta.json (written by run.sh: the run's window
and its Prometheus), then prints a markdown table, one row per minute:
throughput and errors from k6, latency from k6 and from Django, and each
container's CPU as a share of its limit beside Postgres. The resource that
saturates first is the column that reaches 100 % first. Standard library only.

k6 latency comes in two forms. Runs since #20 send native histograms, so their p95
and mean are per-minute. Older runs have only k6's trend stats, calculated since the
run began: `k6 p95 since start` lags and stays raised after a stall, so never read it
as that minute's latency. Their mean can still be recovered per minute, because
avg x count is a running total (see `per_minute_means`).
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

# Server-side latency of both services: Django's, and the FastAPI catalog's, which has
# the same buckets so one quantile covers both (#37). Older runs have only Django's.
SERVER_LATENCY = (
    "django_http_requests_latency_seconds_by_view_method_bucket",
    "http_request_duration_seconds_bucket",
)
K6_LATENCY = "k6_http_req_duration_seconds"
CACHE_REQUESTS = "app_cache_requests_total"
CACHE_GROUPS = ("dashboard", "dashboard-scores", "pdf", "type-list")


ROLES = (
    "gateway",
    "catalog",
    "instances",
    "db",
    "mongo",
    "cache",
    "loadgen",
    "monitor",
)
# Guest 241 was saas-app until #21, and older runs' samples keep that label.
PREVIOUS_INSTANCES = {"catalog": "saas-app"}


def cpu_share(role: str) -> str:
    names = [f"saas-{role}"]
    if role in PREVIOUS_INSTANCES:
        names.append(PREVIOUS_INSTANCES[role])
    instance = f'instance=~"{"|".join(names)}"'
    return (
        f"100 * sum(rate(container_cpu_usage_seconds_total{{{instance}}}[1m]))"
        f" / max(container_cpu_limit_cores{{{instance}}})"
    )


def cache_hit_ratio(group: str) -> str:
    hits = f'sum(rate({CACHE_REQUESTS}{{group="{group}", result="hit"}}[1m]))'
    reads = f'sum(rate({CACHE_REQUESTS}{{group="{group}", result=~"hit|miss"}}[1m]))'
    return f"100 * {hits} / {reads}"


def server_quantile(q: float) -> str:
    rates = " or ".join(f"rate({metric}[1m])" for metric in SERVER_LATENCY)
    return f"1000 * histogram_quantile({q}, sum by (le) ({rates}))"


def k6_worst_group_p95(selector: str) -> str:
    """The slowest endpoint group's p95 over this minute (runs with histograms)."""
    return (
        "1000 * max(histogram_quantile(0.95, sum by (name) "
        f"(rate({K6_LATENCY}{{{selector}}}[1m]))))"
    )


def k6_mean(selector: str) -> str:
    """Mean latency of all requests over this minute (runs with histograms)."""
    rates = f"sum(rate({K6_LATENCY}{{{selector}}}[1m]))"
    return f"1000 * histogram_sum({rates}) / histogram_count({rates})"


def per_minute_means(
    totals: dict[tuple, dict[float, float]],
    counts: dict[tuple, dict[float, float]],
    times: list[float],
) -> dict[float, float]:
    """Mean milliseconds over each step, from k6's running totals, per series.

    `totals` is seconds of latency so far (avg x count), `counts` is requests so
    far, both by series. `times[0]` is only the starting point. k6 stops sending a
    series with no new samples, so it goes stale after 5 minutes and can come back
    later. Each series is therefore compared with its own last known value.
    """
    last: dict[tuple, tuple[float, float]] = {}
    means: dict[float, float] = {}
    for index, t in enumerate(times):
        seconds = requests = 0.0
        for key, by_time in counts.items():
            count = by_time.get(t)
            total = totals.get(key, {}).get(t)
            if count is None or total is None:
                continue
            before_total, before_count = last.get(key, (0.0, 0.0))
            if index > 0 and count > before_count:
                seconds += total - before_total
                requests += count - before_count
            last[key] = (total, count)
        if index > 0 and requests:
            means[t] = 1000 * seconds / requests
    return means


def report_window(start_ms: float, end_ms: float) -> tuple[int, int]:
    """The first full minute after the start, to the last one before the end.

    A run too short to hold one (smoke) gets a single row at the minute it ended.
    """
    start = math.ceil(start_ms / 1000 / STEP) * STEP + STEP
    end = math.floor(end_ms / 1000 / STEP) * STEP
    return min(start, end), end


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
        ("k6 mean ms", k6_mean(k6), "{:.1f}"),
        ("k6 p95 worst group ms", k6_worst_group_p95(k6), "{:.0f}"),
        (
            "k6 p95 since start, worst group ms",
            f"1000 * max(max_over_time(k6_http_req_duration_p95{{{k6}}}[1m]))",
            "{:.0f}",
        ),
        ("server p95 ms", server_quantile(0.95), "{:.0f}"),
        ("server p99 ms", server_quantile(0.99), "{:.0f}"),
        *((f"{role} cpu %", cpu_share(role), "{:.0f}") for role in ROLES),
        *(
            (f"{group} hit %", cache_hit_ratio(group), "{:.0f}")
            for group in CACHE_GROUPS
        ),
        (
            # CONN_MAX_AGE is 0: one connection per request, so a sample is mostly 0.
            "pg conns (sampled)",
            'sum(pg_stat_activity_count{datname=~"appdb|catalogdb|instancesdb"})',
            "{:.0f}",
        ),
        (
            "pg commits/s",
            'sum(rate(pg_stat_database_xact_commit{datname=~"appdb|catalogdb|instancesdb"}[1m]))',
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


def query_series(
    prometheus: str, expr: str, start: float, end: float
) -> dict[tuple, dict[float, float]]:
    """Each series' values by time, keyed by its labels."""
    params = urllib.parse.urlencode(
        {"query": expr, "start": start, "end": end, "step": STEP}
    )
    url = f"{prometheus}/api/v1/query_range?{params}"
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        result = json.load(response)["data"]["result"]
    return {
        tuple(sorted((k, v) for k, v in series["metric"].items() if k != "__name__")): {
            float(t): float(v) for t, v in series["values"]
        }
        for series in result
    }


def old_run_means(
    prometheus: str, testid: str, start: float, end: float
) -> dict[float, float]:
    """Per-minute mean for a run without histograms, from k6's running totals."""
    k6 = f'testid="{testid}"'
    first = start - STEP
    counts = f"k6_http_reqs_total{{{k6}}}"
    totals = f"k6_http_req_duration_avg{{{k6}}} * {counts}"
    times = [float(t) for t in range(int(first), int(end) + 1, STEP)]
    return per_minute_means(
        query_series(prometheus, totals, first, end),
        query_series(prometheus, counts, first, end),
        times,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("testid")
    args = parser.parse_args()
    meta_path = RESULTS / f"{args.testid}.meta.json"
    if not meta_path.exists():
        sys.exit(f"no {meta_path}: run.sh writes it at the end of each run")
    meta = json.loads(meta_path.read_text())
    start, end = report_window(meta["start_ms"], meta["end_ms"])
    cols = columns(args.testid)
    series = [query_range(meta["prometheus"], expr, start, end) for _, expr, _ in cols]
    mean = next(i for i, (header, _, _) in enumerate(cols) if header == "k6 mean ms")
    if not series[mean]:
        series[mean] = old_run_means(meta["prometheus"], args.testid, start, end)

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
