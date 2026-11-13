"""loadtest/report.py and the k6 settings that give it per-minute latency (#20).

k6's trend stats are calculated since the run began, so a figure read from them
lags what the deploy is doing. New runs send native histograms. Old runs' means are
recovered from running totals, which is the arithmetic tested here.
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT = REPO_ROOT / "loadtest" / "report.py"

pytestmark = pytest.mark.skipif(not REPORT.exists(), reason="loadtest/ not present")


@pytest.fixture
def report():
    spec = importlib.util.spec_from_file_location("k6_report", REPORT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = (("name", "a"),)
B = (("name", "b"),)
TIMES = [0.0, 60.0, 120.0, 180.0]


def test_mean_is_per_minute_not_since_the_start(report):
    # 100 requests at 10 ms, then 100 at 110 ms: the running mean would say 60.
    totals = {A: {0.0: 0.0, 60.0: 1.0, 120.0: 12.0}}
    counts = {A: {0.0: 0.0, 60.0: 100.0, 120.0: 200.0}}

    means = report.per_minute_means(totals, counts, TIMES[:3])

    assert means == pytest.approx({60.0: 10.0, 120.0: 110.0})


def test_mean_weights_series_by_their_requests(report):
    totals = {A: {0.0: 0.0, 60.0: 1.0}, B: {0.0: 0.0, 60.0: 9.0}}
    counts = {A: {0.0: 0.0, 60.0: 100.0}, B: {0.0: 0.0, 60.0: 100.0}}

    assert report.per_minute_means(totals, counts, TIMES[:2]) == pytest.approx(
        {60.0: 50.0}
    )


def test_series_going_stale_does_not_turn_the_mean_negative(report):
    # B stops being sent, as k6 does for `token` after startup logins.
    totals = {A: {0.0: 0.0, 60.0: 1.0, 120.0: 2.0}, B: {0.0: 50.0, 60.0: 50.0}}
    counts = {A: {0.0: 0.0, 60.0: 100.0, 120.0: 200.0}, B: {0.0: 100.0, 60.0: 100.0}}

    means = report.per_minute_means(totals, counts, TIMES[:3])

    assert means == pytest.approx({60.0: 10.0, 120.0: 10.0})


def test_series_coming_back_adds_only_its_new_requests(report):
    # B's running total of 50 s is old. Only the 10 new requests count.
    totals = {
        A: {0.0: 0.0, 60.0: 1.0, 120.0: 2.0, 180.0: 3.0},
        B: {0.0: 50.0, 180.0: 51.0},
    }
    counts = {
        A: {0.0: 0.0, 60.0: 100.0, 120.0: 200.0, 180.0: 300.0},
        B: {0.0: 100.0, 180.0: 110.0},
    }

    means = report.per_minute_means(totals, counts, TIMES)

    assert means[60.0] == pytest.approx(10.0)
    assert means[180.0] == pytest.approx(2000 / 110)


def test_series_first_seen_later_counts_from_zero(report):
    totals = {A: {0.0: 0.0, 60.0: 1.0}, B: {60.0: 1.0}}
    counts = {A: {0.0: 0.0, 60.0: 100.0}, B: {60.0: 100.0}}

    assert report.per_minute_means(totals, counts, TIMES[:2]) == pytest.approx(
        {60.0: 10.0}
    )


def test_minute_without_requests_has_no_mean(report):
    totals = {A: {0.0: 1.0, 60.0: 1.0}}
    counts = {A: {0.0: 100.0, 60.0: 100.0}}

    assert report.per_minute_means(totals, counts, TIMES[:2]) == {}


def test_p95_column_reads_histograms_and_old_one_is_labelled(report):
    columns = {header: expr for header, expr, _ in report.columns("run-1")}

    assert "histogram_quantile" in columns["k6 p95 worst group ms"]
    assert "k6_http_req_duration_seconds" in columns["k6 p95 worst group ms"]
    assert "k6_http_req_duration_seconds" in columns["k6 mean ms"]
    assert "k6_http_req_duration_p95" in columns["k6 p95 since start, worst group ms"]


def test_catalog_cpu_reads_the_container_under_both_names(report):
    # Guest 241 was renamed in #21: new runs have one label, older runs the other.
    expr = {header: expr for header, expr, _ in report.columns("run-1")}[
        "catalog cpu %"
    ]

    assert 'instance=~"saas-catalog|saas-app"' in expr


def test_other_containers_read_only_their_own_name(report):
    assert 'instance=~"saas-instances"' in report.cpu_share("instances")
    assert "saas-app" not in report.cpu_share("instances")


def test_window_covers_only_full_minutes(report):
    # 00:00:30 to 00:05:30: the first full minute after the start ends at 00:02:00.
    assert report.report_window(30_000, 330_000) == (120, 300)


def test_run_too_short_for_a_full_minute_still_gets_one_row(report):
    # 00:00:30 to 00:01:30, as a smoke run can be. Prometheus refuses end < start.
    assert report.report_window(30_000, 90_000) == (60, 60)


@pytest.mark.parametrize(
    "path",
    [
        "infra/ansible/roles/loadgen/templates/k6.env.j2",
        "infra/docker/docker-compose.loadtest.yml",
    ],
)
def test_stacks_send_native_histograms(path):
    text = (REPO_ROOT / path).read_text()
    assert "K6_PROMETHEUS_RW_TREND_AS_NATIVE_HISTOGRAM" in text
    assert "K6_PROMETHEUS_RW_TREND_STATS" not in text


def test_server_latency_covers_both_services(report):
    query = report.server_quantile(0.95)
    assert "django_http_requests_latency_seconds_by_view_method_bucket" in query
    assert "http_request_duration_seconds_bucket" in query
    assert " or " in query
