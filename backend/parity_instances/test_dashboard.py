"""The dashboards: fixed rows, moved in time, read in several time zones (#19).

A window of `days` starts at midnight in `tz`, `days - 1` days ago. KPIs and per-type
counts follow the questionnaires *created* in the window; activity follows
`submittedAt`. Floats are compared at the precision the service rounds to.

`range.from` and `range.to` carry the zone's offset (`Z` for UTC); every other
timestamp is UTC, as on every endpoint. All keep microseconds.
"""

import re
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from .support import create_battery, create_questionnaire, parse_time, submit

SUMMARY = "/api/dashboard/"
SCORES = "/api/dashboard/scores/"
DASHBOARD_TIME = r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{6})?(Z|[+-]\d\d:\d\d)$"
ZONES = ["UTC", "America/New_York", "Australia/Sydney", "Asia/Kolkata"]
SCORE_POINT_LIMIT = 500


def make(owner, anon, clock, qtype_id, created, submitted=None, name="", metrics=None):
    """A questionnaire created at `created`, submitted at `submitted` if given."""
    row = create_questionnaire(owner, qtype_id, name=name)
    if submitted is not None:
        assert submit(anon, row["shareToken"], {}, metrics).status_code == 200
    clock.set(row["id"], created_at=created, submitted_at=submitted)
    return row


def get(owner, path: str, **params) -> dict:
    response = owner.http.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def same_instant(value: str, expected: datetime) -> bool:
    assert re.match(DASHBOARD_TIME, value), value
    return parse_time(value) == expected


def local_midnight(day: date, tz: ZoneInfo) -> str:
    return datetime.combine(day, time.min, tzinfo=tz).isoformat().replace("+00:00", "Z")


def by_day(body: dict) -> dict[str, int]:
    return {entry["date"]: entry["count"] for entry in body["submissionsByDay"]}


def assert_contiguous(series: list[dict], first: date, last: date) -> None:
    expected = [
        (first + timedelta(days=offset)).isoformat()
        for offset in range((last - first).days + 1)
    ]
    assert [entry["date"] for entry in series] == expected


# ── Summary ──────────────────────────────────────────────────────────────────


@pytest.fixture
def rows(catalog, owner, anon, clock):
    now = datetime.now(UTC)
    alpha = catalog.qtype(owner, title="Alpha")["aggregateId"]
    beta = catalog.qtype(owner, title="Beta")["aggregateId"]
    hour = timedelta(hours=1)
    day = timedelta(days=1)
    q = {
        # 24 h to complete, submitted outside a 7-day window.
        "one": make(
            owner, anon, clock, alpha, now - 10 * day, now - 9 * day, name="One"
        ),
        "two": make(
            owner,
            anon,
            clock,
            alpha,
            now - 3 * day,
            now - 3 * day + 2 * hour,
            name="Two",
        ),
        "three": make(owner, anon, clock, alpha, now - 2 * day),
        # Pending for over a week: listed whatever the window.
        "four": make(owner, anon, clock, alpha, now - 20 * day, name="Four"),
        "five": make(
            owner, anon, clock, beta, now - hour, now - 24 * timedelta(minutes=1)
        ),
    }
    return now, alpha, beta, q


def test_all_time(owner, rows):
    now, alpha, beta, q = rows
    body = get(owner, SUMMARY)
    assert set(body) == {
        "range",
        "kpis",
        "submissionsByDay",
        "byQuestionnaireType",
        "byBatteryType",
        "recentSubmissions",
        "stalePending",
    }
    assert body["range"]["days"] is None
    assert body["range"]["from"] is None
    assert same_instant(body["range"]["to"], parse_time(body["range"]["to"]))
    assert body["range"]["to"].endswith("Z")
    assert abs(parse_time(body["range"]["to"]) - now) < timedelta(minutes=1)
    assert body["kpis"] == {
        "questionnairesSent": 5,
        "questionnairesSubmitted": 3,
        "questionnairesPending": 2,
        "completionRate": 0.6,
        # Of 24, 2 and 0.6 hours.
        "medianHoursToComplete": 2.0,
        "batteriesTotal": 0,
        "batteriesComplete": 0,
        "batteriesInProgress": 0,
        "batteriesNotStarted": 0,
    }
    assert body["byQuestionnaireType"] == [
        {"id": alpha, "title": "Alpha", "sent": 4, "submitted": 2, "pending": 2},
        {"id": beta, "title": "Beta", "sent": 1, "submitted": 1, "pending": 0},
    ]
    assert body["byBatteryType"] == []
    recent = body["recentSubmissions"]
    assert [r["id"] for r in recent] == [
        q["five"]["id"],
        q["two"]["id"],
        q["one"]["id"],
    ]
    assert recent[1] | {"submittedAt": None} == {
        "id": q["two"]["id"],
        "name": "Two",
        "questionnaireTypeTitle": "Alpha",
        "submittedAt": None,
    }
    assert same_instant(
        recent[1]["submittedAt"], now - 3 * timedelta(days=1) + timedelta(hours=2)
    )
    (stale,) = body["stalePending"]
    assert stale | {"createdAt": None} == {
        "id": q["four"]["id"],
        "name": "Four",
        "questionnaireTypeTitle": "Alpha",
        "shareToken": q["four"]["shareToken"],
        "createdAt": None,
        "ageDays": 20,
    }
    assert same_instant(stale["createdAt"], now - timedelta(days=20))
    # All time: from the first submission's day to today.
    series = body["submissionsByDay"]
    assert_contiguous(series, (now - timedelta(days=9)).date(), now.date())
    assert sum(entry["count"] for entry in series) == 3


def test_seven_days(owner, rows):
    now, alpha, beta, q = rows
    body = get(owner, SUMMARY, days=7)
    start = now.date() - timedelta(days=6)
    assert body["range"]["days"] == 7
    assert body["range"]["from"] == local_midnight(start, ZoneInfo("UTC"))
    assert body["kpis"] == {
        "questionnairesSent": 3,
        "questionnairesSubmitted": 2,
        "questionnairesPending": 1,
        "completionRate": 0.6667,
        # Of 2 and 0.6 hours.
        "medianHoursToComplete": 1.3,
        "batteriesTotal": 0,
        "batteriesComplete": 0,
        "batteriesInProgress": 0,
        "batteriesNotStarted": 0,
    }
    assert body["byQuestionnaireType"] == [
        {"id": alpha, "title": "Alpha", "sent": 2, "submitted": 1, "pending": 1},
        {"id": beta, "title": "Beta", "sent": 1, "submitted": 1, "pending": 0},
    ]
    assert [r["id"] for r in body["recentSubmissions"]] == [
        q["five"]["id"],
        q["two"]["id"],
    ]
    assert [s["id"] for s in body["stalePending"]] == [q["four"]["id"]]
    assert_contiguous(body["submissionsByDay"], start, now.date())
    assert sum(by_day(body).values()) == 2


def test_filtered_by_type(owner, rows):
    _, _, beta, q = rows
    body = get(owner, SUMMARY, questionnaireType=beta)
    assert body["kpis"]["questionnairesSent"] == 1
    assert body["kpis"]["questionnairesSubmitted"] == 1
    assert body["kpis"]["completionRate"] == 1.0
    assert [t["id"] for t in body["byQuestionnaireType"]] == [beta]
    assert [r["id"] for r in body["recentSubmissions"]] == [q["five"]["id"]]
    assert body["stalePending"] == []


def test_an_empty_dashboard(owner):
    body = get(owner, SUMMARY)
    assert body["kpis"]["questionnairesSent"] == 0
    assert body["kpis"]["completionRate"] == 0.0
    assert body["kpis"]["medianHoursToComplete"] is None
    assert body["submissionsByDay"] == []
    assert body["recentSubmissions"] == []
    assert body["stalePending"] == []
    # A window always has its days, even with nothing in them.
    week = get(owner, SUMMARY, days=7)
    assert [entry["count"] for entry in week["submissionsByDay"]] == [0] * 7


def test_another_owners_rows_never_show(owner, other, rows):  # noqa: ARG001
    body = get(other, SUMMARY)
    assert body["kpis"]["questionnairesSent"] == 0
    assert body["byQuestionnaireType"] == []


def test_lists_hold_ten(catalog, owner, anon, clock):
    qtype_id = catalog.qtype(owner)["aggregateId"]
    now = datetime.now(UTC)
    for minutes in range(12):
        submitted = now - timedelta(minutes=minutes)
        make(owner, anon, clock, qtype_id, submitted - timedelta(minutes=5), submitted)
        make(owner, anon, clock, qtype_id, now - timedelta(days=8, minutes=minutes))
    body = get(owner, SUMMARY)
    assert len(body["recentSubmissions"]) == 10
    assert len(body["stalePending"]) == 10
    # Newest submission first; oldest pending first.
    recent = [parse_time(r["submittedAt"]) for r in body["recentSubmissions"]]
    assert recent == sorted(recent, reverse=True)
    stale = [parse_time(s["createdAt"]) for s in body["stalePending"]]
    assert stale == sorted(stale)
    assert [s["ageDays"] for s in body["stalePending"]] == [8] * 10


# ── Batteries ────────────────────────────────────────────────────────────────


def test_battery_status(catalog, owner, anon):
    alpha = catalog.qtype(owner, title="Alpha")["aggregateId"]
    beta = catalog.qtype(owner, title="Beta")["aggregateId"]
    kit = catalog.btype(owner, [alpha, beta], title="Kit")["aggregateId"]
    unused = catalog.btype(owner, [beta], title="Unused")["aggregateId"]
    batteries = [create_battery(owner, kit, name=f"B{i}") for i in range(3)]
    submit(anon, batteries[1]["questionnaires"][0]["shareToken"])
    for slot in batteries[2]["questionnaires"]:
        submit(anon, slot["shareToken"])

    body = get(owner, SUMMARY)
    kpis = body["kpis"]
    assert (
        kpis["batteriesTotal"],
        kpis["batteriesComplete"],
        kpis["batteriesInProgress"],
        kpis["batteriesNotStarted"],
    ) == (3, 1, 1, 1)
    assert body["byBatteryType"] == [
        {"id": kit, "title": "Kit", "complete": 1, "inProgress": 1, "notStarted": 1},
        {
            "id": unused,
            "title": "Unused",
            "complete": 0,
            "inProgress": 0,
            "notStarted": 0,
        },
    ]
    # A battery's questionnaires have no name of their own: the battery's is shown.
    assert {r["name"] for r in body["recentSubmissions"]} == {"B1", "B2"}

    # Filtered by a type, a battery still counts all of its slots.
    filtered = get(owner, SUMMARY, questionnaireType=alpha)
    assert filtered["kpis"]["batteriesTotal"] == 3
    assert filtered["kpis"]["batteriesComplete"] == 1
    assert [b["id"] for b in filtered["byBatteryType"]] == [kit]


# ── Time zones ───────────────────────────────────────────────────────────────


def last_transition(tz: ZoneInfo, now: datetime) -> datetime:
    """The latest instant before `now` at which `tz` changed its offset."""
    moment = now.replace(minute=0, second=0, microsecond=0)
    after = moment.astimezone(tz).utcoffset()
    for _ in range(24 * 400):
        earlier = moment - timedelta(hours=1)
        if earlier.astimezone(tz).utcoffset() != after:
            return moment
        moment = earlier
    raise AssertionError(f"{tz} has not changed offset in 400 days")


def test_days_are_bucketed_in_the_zone_across_a_dst_change(catalog, owner, anon, clock):
    new_york = ZoneInfo("America/New_York")
    now = datetime.now(UTC)
    change = last_transition(new_york, now)
    qtype_id = catalog.qtype(owner)["aggregateId"]
    moments = [change + timedelta(hours=h) for h in (-20, -3, -1, 1, 3, 20)]
    for moment in moments:
        make(owner, anon, clock, qtype_id, moment - timedelta(hours=1), moment)

    for name in [*ZONES, "Europe/London"]:
        tz = ZoneInfo(name)
        body = get(owner, SUMMARY, tz=name)
        expected = Counter(
            moment.astimezone(tz).date().isoformat() for moment in moments
        )
        counts = {day: count for day, count in by_day(body).items() if count}
        assert counts == dict(expected), name
        first = min(moment.astimezone(tz).date() for moment in moments)
        assert_contiguous(body["submissionsByDay"], first, now.astimezone(tz).date())
        # Submitted times are instants: the same in every zone.
        recent = {parse_time(r["submittedAt"]) for r in body["recentSubmissions"]}
        assert len(recent) == len(moments)

    # The zone matters: New York and UTC disagree about which day some fell on.
    utc_days = Counter(m.date().isoformat() for m in moments)
    ny_days = Counter(m.astimezone(new_york).date().isoformat() for m in moments)
    assert utc_days != ny_days


@pytest.mark.parametrize("name", ZONES)
@pytest.mark.parametrize("days", [7, 30, 90])
def test_a_window_starts_at_midnight_in_the_zone(owner, name, days):
    tz = ZoneInfo(name)
    body = get(owner, SUMMARY, days=days, tz=name)
    to = body["range"]["to"]
    assert re.match(DASHBOARD_TIME, to)
    now = datetime.now(tz)
    assert parse_time(to).utcoffset() == now.utcoffset()
    assert abs(parse_time(to) - now) < timedelta(minutes=1)
    today = parse_time(to).date()
    # Its own offset: across a DST change it differs from `to`'s.
    assert body["range"]["from"] == local_midnight(today - timedelta(days=days - 1), tz)
    assert len(body["submissionsByDay"]) == days


def test_a_window_counts_from_local_midnight(catalog, owner, anon, clock):
    """A submission just before local midnight `days - 1` days ago is outside."""
    name = "Australia/Sydney"
    tz = ZoneInfo(name)
    qtype_id = catalog.qtype(owner)["aggregateId"]
    today = datetime.now(tz).date()
    start = datetime.combine(today - timedelta(days=6), time.min, tzinfo=tz)
    inside = start + timedelta(minutes=1)
    outside = start - timedelta(minutes=1)
    make(owner, anon, clock, qtype_id, inside - timedelta(hours=1), inside)
    make(owner, anon, clock, qtype_id, outside - timedelta(hours=1), outside)
    body = get(owner, SUMMARY, days=7, tz=name)
    assert sum(by_day(body).values()) == 1
    assert by_day(body)[start.date().isoformat()] == 1


# ── Validation ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"days": "5"}, "days"),
        ({"days": "abc"}, "days"),
        ({"tz": "Nowhere/City"}, "tz"),
        ({"tz": "America"}, "tz"),
        ({"tz": "../../etc/passwd"}, "tz"),
        ({"tz": "x" * 65}, "tz"),
        ({"questionnaireType": "not-a-uuid"}, "questionnaireType"),
    ],
)
@pytest.mark.parametrize("path", [SUMMARY, SCORES])
def test_bad_parameters_are_400(owner, qtype, path, params, field):
    if path == SCORES:
        params = {"questionnaireType": qtype["aggregateId"], **params}
    response = owner.http.get(path, params=params)
    assert response.status_code == 400
    assert field in response.json()


def test_another_owners_type_is_400(catalog, owner, other):
    theirs = catalog.qtype(other)["aggregateId"]
    for path in (SUMMARY, SCORES):
        response = owner.http.get(path, params={"questionnaireType": theirs})
        assert response.status_code == 400
        assert set(response.json()) == {"questionnaireType"}


def test_scores_need_a_type(owner):
    response = owner.http.get(SCORES)
    assert response.status_code == 400
    assert set(response.json()) == {"questionnaireType"}


# ── Scores ───────────────────────────────────────────────────────────────────


SCORED = {
    "pages": [],
    "calculatedValues": [
        {"name": "total", "title": "Total score", "expression": "1"},
        {"name": "severity", "expression": "'x'"},
    ],
}


def test_scores(catalog, owner, anon, clock):
    qtype_id = catalog.qtype(owner, questionnaire_json=SCORED)["aggregateId"]
    now = datetime.now(UTC)
    stored = [
        {"total": 5, "severity": "mild", "flag": True, "extra": 1.5},
        {"total": 7, "severity": "mild", "flag": False},
        # Not a number: skipped for `total`, whose first value was one.
        {"total": "x", "severity": "severe", "ignored": None, "nested": {"a": 1}},
        {"total": 10},
    ]
    made = []
    for index, metrics in enumerate(stored):
        submitted = now - timedelta(hours=len(stored) - index)
        made.append(
            make(
                owner,
                anon,
                clock,
                qtype_id,
                submitted - timedelta(hours=1),
                submitted,
                name=f"R{index}",
                metrics=metrics,
            )
        )
    # Not submitted: never counted.
    make(owner, anon, clock, qtype_id, now - timedelta(hours=1))

    body = get(owner, SCORES, questionnaireType=qtype_id)
    assert body["questionnaireTypeId"] == qtype_id
    metrics = {m["name"]: m for m in body["metrics"]}
    # The type's order, then the rest by name.
    assert [m["name"] for m in body["metrics"]] == [
        "total",
        "severity",
        "extra",
        "flag",
    ]

    total = metrics["total"]
    assert set(total) == {"name", "label", "kind", "count", "points", "mean"}
    assert (total["label"], total["kind"], total["count"]) == (
        "Total score",
        "numeric",
        3,
    )
    assert total["mean"] == round(22 / 3, 2)
    assert [p["value"] for p in total["points"]] == [5, 7, 10]
    assert [p["questionnaireId"] for p in total["points"]] == [
        made[0]["id"],
        made[1]["id"],
        made[3]["id"],
    ]
    assert [p["name"] for p in total["points"]] == ["R0", "R1", "R3"]
    assert set(total["points"][0]) == {
        "questionnaireId",
        "name",
        "submittedAt",
        "value",
    }
    assert same_instant(total["points"][0]["submittedAt"], now - timedelta(hours=4))

    severity = metrics["severity"]
    assert set(severity) == {"name", "label", "kind", "count", "points", "distribution"}
    assert (severity["label"], severity["kind"], severity["count"]) == (
        "severity",
        "categorical",
        3,
    )
    assert severity["distribution"] == [
        {"value": "mild", "count": 2},
        {"value": "severe", "count": 1},
    ]

    flag = metrics["flag"]
    assert (flag["kind"], flag["count"]) == ("boolean", 2)
    # Most common first, then by the value as text: "False" before "True".
    assert flag["distribution"] == [
        {"value": False, "count": 1},
        {"value": True, "count": 1},
    ]
    assert metrics["extra"]["mean"] == 1.5
    assert metrics["extra"]["label"] == "extra"


def test_scores_of_a_type_with_no_submissions(owner, qtype):
    body = get(owner, SCORES, questionnaireType=qtype["aggregateId"])
    assert body == {"questionnaireTypeId": qtype["aggregateId"], "metrics": []}


def test_scores_follow_the_window(catalog, owner, anon, clock):
    qtype_id = catalog.qtype(owner)["aggregateId"]
    now = datetime.now(UTC)
    make(
        owner,
        anon,
        clock,
        qtype_id,
        now - timedelta(days=11),
        now - timedelta(days=10),
        metrics={"s": 1},
    )
    make(
        owner,
        anon,
        clock,
        qtype_id,
        now - timedelta(hours=2),
        now - timedelta(hours=1),
        metrics={"s": 3},
    )
    week = get(owner, SCORES, questionnaireType=qtype_id, days=7)["metrics"][0]
    assert (week["count"], week["mean"]) == (1, 3.0)
    ever = get(owner, SCORES, questionnaireType=qtype_id)["metrics"][0]
    assert (ever["count"], ever["mean"]) == (2, 2.0)


def test_points_are_capped_but_totals_cover_the_window(catalog, owner, anon):
    qtype_id = catalog.qtype(owner)["aggregateId"]
    size = SCORE_POINT_LIMIT + 1
    battery = create_battery(
        owner, catalog.btype(owner, [qtype_id] * size)["aggregateId"], name="Big"
    )
    for value, slot in enumerate(battery["questionnaires"]):
        assert submit(anon, slot["shareToken"], {}, {"s": value}).status_code == 200

    (metric,) = get(owner, SCORES, questionnaireType=qtype_id)["metrics"]
    assert metric["count"] == size
    assert metric["mean"] == round(sum(range(size)) / size, 2)
    # Only the latest, oldest first: the very first submission is left out.
    assert [p["value"] for p in metric["points"]] == list(range(1, size))
    assert {p["name"] for p in metric["points"]} == {"Big"}
