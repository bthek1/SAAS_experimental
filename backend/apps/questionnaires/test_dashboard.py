from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time

from . import services
from .factories import (
    BatteryTypeFactory,
    QuestionnaireFactory,
    QuestionnaireTypeFactory,
)

URL = "/api/dashboard/"
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def submit(q, when=None):
    with freeze_time(when or NOW):
        return services.submit_questionnaire(q, {"q1": "a"}, {})


def make_questionnaire(qtype, created, **kwargs):
    with freeze_time(created):
        return QuestionnaireFactory(questionnaire_type=qtype, **kwargs)


def get(client, **params):
    with freeze_time(NOW):
        return client.get(URL, params)


# ── Auth and ownership ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_dashboard_requires_auth(api_client):
    assert api_client.get(URL).status_code == 401


def test_dashboard_only_counts_own_rows(auth_client, qtype, other_user):
    other_type = QuestionnaireTypeFactory(owner=other_user)
    submit(make_questionnaire(other_type, NOW))
    services.create_battery(
        BatteryTypeFactory(owner=other_user, questionnaire_types=[other_type])
    )
    make_questionnaire(qtype, NOW)

    data = get(auth_client).json()

    assert data["kpis"]["questionnairesSent"] == 1
    assert data["kpis"]["questionnairesSubmitted"] == 0
    assert data["kpis"]["batteriesTotal"] == 0
    assert [t["id"] for t in data["byQuestionnaireType"]] == [str(qtype.id)]
    assert data["byBatteryType"] == []
    assert data["recentSubmissions"] == []


# ── KPIs ──────────────────────────────────────────────────────────────────────


def test_kpis_empty_account(auth_client, user):  # noqa: ARG001
    data = get(auth_client).json()
    assert data["kpis"] == {
        "questionnairesSent": 0,
        "questionnairesSubmitted": 0,
        "questionnairesPending": 0,
        "completionRate": 0.0,
        "medianHoursToComplete": None,
        "batteriesTotal": 0,
        "batteriesComplete": 0,
        "batteriesInProgress": 0,
        "batteriesNotStarted": 0,
    }
    assert data["submissionsByDay"] == []
    assert data["range"]["days"] is None


def test_kpis_counts_and_completion_rate(auth_client, qtype):
    created = NOW - timedelta(days=2)
    submit(make_questionnaire(qtype, created), created + timedelta(hours=1))
    submit(make_questionnaire(qtype, created), created + timedelta(hours=3))
    submit(make_questionnaire(qtype, created), created + timedelta(hours=8))
    make_questionnaire(qtype, created)

    data = get(auth_client).json()

    assert data["kpis"]["questionnairesSent"] == 4
    assert data["kpis"]["questionnairesSubmitted"] == 3
    assert data["kpis"]["questionnairesPending"] == 1
    assert data["kpis"]["completionRate"] == 0.75
    assert data["kpis"]["medianHoursToComplete"] == 3.0
    assert data["byQuestionnaireType"] == [
        {
            "id": str(qtype.id),
            "title": qtype.title,
            "sent": 4,
            "submitted": 3,
            "pending": 1,
        }
    ]


def test_battery_status_buckets(auth_client, user):
    first, second = (
        QuestionnaireTypeFactory(owner=user),
        QuestionnaireTypeFactory(owner=user),
    )
    btype = BatteryTypeFactory(
        owner=user, title="Intake", questionnaire_types=[first, second]
    )
    BatteryTypeFactory(owner=user, title="Unused")

    services.create_battery(btype)  # not started
    in_progress = services.create_battery(btype)
    submit(in_progress.questionnaires.get(battery_order=0))
    complete = services.create_battery(btype)
    for q in complete.questionnaires.all():
        submit(q)

    data = get(auth_client).json()

    assert data["kpis"]["batteriesTotal"] == 3
    assert data["kpis"]["batteriesComplete"] == 1
    assert data["kpis"]["batteriesInProgress"] == 1
    assert data["kpis"]["batteriesNotStarted"] == 1
    assert data["byBatteryType"] == [
        {
            "id": str(btype.id),
            "title": "Intake",
            "complete": 1,
            "inProgress": 1,
            "notStarted": 1,
        },
        {
            "id": data["byBatteryType"][1]["id"],
            "title": "Unused",
            "complete": 0,
            "inProgress": 0,
            "notStarted": 0,
        },
    ]


# ── Window and filters ────────────────────────────────────────────────────────


def test_days_window_filters_and_zero_fills(auth_client, qtype):
    old = make_questionnaire(qtype, NOW - timedelta(days=20))
    submit(old, NOW - timedelta(days=19))
    recent = make_questionnaire(qtype, NOW - timedelta(days=3))
    submit(recent, NOW - timedelta(days=1))
    make_questionnaire(qtype, NOW)

    data = get(auth_client, days=7).json()

    assert data["range"]["days"] == 7
    assert data["range"]["from"].startswith("2026-10-24T00:00:00")
    assert data["kpis"]["questionnairesSent"] == 2
    assert data["kpis"]["questionnairesSubmitted"] == 1
    days = data["submissionsByDay"]
    assert [d["date"] for d in days] == [f"2026-10-{d}" for d in range(24, 31)]
    assert [d["count"] for d in days] == [0, 0, 0, 0, 0, 1, 0]
    assert [r["id"] for r in data["recentSubmissions"]] == [str(recent.id)]

    all_time = get(auth_client).json()
    assert all_time["kpis"]["questionnairesSent"] == 3
    assert all_time["submissionsByDay"][0]["date"] == "2026-10-11"
    assert sum(d["count"] for d in all_time["submissionsByDay"]) == 2


def test_stale_pending_ignores_window(auth_client, qtype):
    stale = make_questionnaire(qtype, NOW - timedelta(days=40), name="Pat")
    make_questionnaire(qtype, NOW - timedelta(days=2))  # pending, not stale yet
    submit(make_questionnaire(qtype, NOW - timedelta(days=30)))

    data = get(auth_client, days=7).json()

    assert data["stalePending"] == [
        {
            "id": str(stale.id),
            "name": "Pat",
            "questionnaireTypeTitle": qtype.title,
            "shareToken": str(stale.share_token),
            "createdAt": data["stalePending"][0]["createdAt"],
            "ageDays": 40,
        }
    ]


def test_questionnaire_type_filter(auth_client, user, qtype):
    other = QuestionnaireTypeFactory(owner=user)
    make_questionnaire(qtype, NOW)
    make_questionnaire(other, NOW)
    btype = BatteryTypeFactory(owner=user, questionnaire_types=[qtype, other])
    battery = services.create_battery(btype)
    submit(battery.questionnaires.get(questionnaire_type=qtype))
    BatteryTypeFactory(owner=user, questionnaire_types=[other])

    data = get(auth_client, questionnaireType=qtype.id).json()

    assert [t["id"] for t in data["byQuestionnaireType"]] == [str(qtype.id)]
    assert data["kpis"]["questionnairesSent"] == 2
    # The battery still counts all of its slots, not only this type's.
    assert data["kpis"]["batteriesInProgress"] == 1
    assert [b["id"] for b in data["byBatteryType"]] == [str(btype.id)]


def test_questionnaire_type_filter_rejects_foreign_type(auth_client, other_user):
    foreign = QuestionnaireTypeFactory(owner=other_user)
    response = get(auth_client, questionnaireType=foreign.id)
    assert response.status_code == 400
    assert "questionnaireType" in response.json()


def test_days_rejects_unsupported_value(auth_client, user):  # noqa: ARG001
    response = get(auth_client, days=5)
    assert response.status_code == 400
    assert "days" in response.json()


# ── Performance ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("rows", [1, 8])
def test_dashboard_query_count(auth_client, user, django_assert_max_num_queries, rows):
    qtypes = [QuestionnaireTypeFactory(owner=user) for _ in range(rows)]
    btype = BatteryTypeFactory(owner=user, questionnaire_types=qtypes)
    for qt in qtypes:
        submit(make_questionnaire(qt, NOW - timedelta(days=10)))
        services.create_battery(btype)

    with django_assert_max_num_queries(10):
        assert get(auth_client).status_code == 200


# ── Scores ────────────────────────────────────────────────────────────────────

SCORES_URL = "/api/dashboard/scores/"
SCORED_JSON = {
    "pages": [],
    "calculatedValues": [
        {"name": "total", "title": "Total score", "expression": "{a} + {b}"},
        {"name": "severity", "title": "Severity", "expression": "..."},
        {"name": "flag", "expression": "{a} > 2"},
    ],
}


@pytest.fixture
def scored_type(user):
    return QuestionnaireTypeFactory(owner=user, questionnaire_json=SCORED_JSON)


def submit_metrics(qtype, metrics, when, name=""):
    q = make_questionnaire(qtype, when - timedelta(hours=1), name=name)
    with freeze_time(when):
        return services.submit_questionnaire(q, {}, metrics)


def get_scores(client, **params):
    with freeze_time(NOW):
        return client.get(SCORES_URL, params)


def metric(data, name):
    return next(m for m in data["metrics"] if m["name"] == name)


def test_scores_numeric_series_ordered_by_submitted_at(auth_client, scored_type):
    later = submit_metrics(scored_type, {"total": 12}, NOW - timedelta(days=1), "B")
    earlier = submit_metrics(scored_type, {"total": 4.5}, NOW - timedelta(days=3), "A")

    data = get_scores(auth_client, questionnaireType=scored_type.id).json()

    total = metric(data, "total")
    assert total["label"] == "Total score"
    assert total["kind"] == "numeric"
    assert [p["questionnaireId"] for p in total["points"]] == [
        str(earlier.id),
        str(later.id),
    ]
    assert [p["value"] for p in total["points"]] == [4.5, 12]
    assert [p["name"] for p in total["points"]] == ["A", "B"]
    assert total["mean"] == 8.25
    assert "distribution" not in total


def test_scores_categorical_distribution(auth_client, scored_type):
    for severity in ["Mild", "Severe", "Mild", "Minimal", "Mild"]:
        submit_metrics(scored_type, {"severity": severity}, NOW)

    severity = metric(
        get_scores(auth_client, questionnaireType=scored_type.id).json(), "severity"
    )

    assert severity["kind"] == "categorical"
    assert severity["distribution"] == [
        {"value": "Mild", "count": 3},
        {"value": "Minimal", "count": 1},
        {"value": "Severe", "count": 1},
    ]


def test_scores_boolean_flags(auth_client, scored_type):
    flagged = submit_metrics(scored_type, {"flag": True, "total": 1}, NOW, "Pat")
    submit_metrics(scored_type, {"flag": False, "total": 2}, NOW)

    data = get_scores(auth_client, questionnaireType=scored_type.id).json()

    flag = metric(data, "flag")
    assert flag["kind"] == "boolean"
    assert flag["label"] == "flag"  # no title in the definition
    assert flag["distribution"] == [
        {"value": False, "count": 1},
        {"value": True, "count": 1},
    ]
    assert [p["questionnaireId"] for p in flag["points"] if p["value"]] == [
        str(flagged.id)
    ]
    # Booleans are not mistaken for numbers (True is an int in Python).
    assert metric(data, "total")["mean"] == 1.5


def test_scores_follow_definition_order_then_unknown_names(auth_client, scored_type):
    submit_metrics(
        scored_type, {"zeta": 1, "flag": True, "total": 3, "alpha": "x"}, NOW
    )
    data = get_scores(auth_client, questionnaireType=scored_type.id).json()
    assert [m["name"] for m in data["metrics"]] == ["total", "flag", "alpha", "zeta"]
    assert metric(data, "zeta")["label"] == "zeta"


def test_scores_skip_values_of_another_kind(auth_client, scored_type):
    submit_metrics(scored_type, {"total": 5}, NOW - timedelta(days=1))
    submit_metrics(scored_type, {"total": "n/a", "severity": None}, NOW)

    data = get_scores(auth_client, questionnaireType=scored_type.id).json()

    assert [p["value"] for p in metric(data, "total")["points"]] == [5]
    assert [m["name"] for m in data["metrics"]] == ["total"]


def test_scores_ignores_pending_and_other_owners(auth_client, scored_type, other_user):
    make_questionnaire(scored_type, NOW)  # pending
    other_type = QuestionnaireTypeFactory(
        owner=other_user, questionnaire_json=SCORED_JSON
    )
    submit_metrics(other_type, {"total": 99}, NOW)
    submit_metrics(scored_type, {"total": 3}, NOW)

    data = get_scores(auth_client, questionnaireType=scored_type.id).json()

    assert data["questionnaireTypeId"] == str(scored_type.id)
    assert [p["value"] for p in metric(data, "total")["points"]] == [3]


def test_scores_days_window(auth_client, scored_type):
    submit_metrics(scored_type, {"total": 1}, NOW - timedelta(days=40))
    submit_metrics(scored_type, {"total": 2}, NOW - timedelta(days=2))

    data = get_scores(auth_client, questionnaireType=scored_type.id, days=30).json()

    assert [p["value"] for p in metric(data, "total")["points"]] == [2]


@pytest.mark.django_db
def test_scores_requires_auth(api_client):
    assert api_client.get(SCORES_URL).status_code == 401


def test_scores_requires_type(auth_client, user):  # noqa: ARG001
    response = get_scores(auth_client)
    assert response.status_code == 400
    assert "questionnaireType" in response.json()


def test_scores_rejects_foreign_type(auth_client, other_user):
    foreign = QuestionnaireTypeFactory(owner=other_user)
    assert get_scores(auth_client, questionnaireType=foreign.id).status_code == 400


def test_scores_query_count(auth_client, scored_type, django_assert_max_num_queries):
    for i in range(6):
        submit_metrics(scored_type, {"total": i, "severity": "Mild"}, NOW)
    with django_assert_max_num_queries(4):
        assert (
            get_scores(auth_client, questionnaireType=scored_type.id).status_code == 200
        )


def test_battery_questionnaires_use_the_battery_name(auth_client, user, scored_type):
    btype = BatteryTypeFactory(owner=user, questionnaire_types=[scored_type])
    with freeze_time(NOW - timedelta(days=10)):
        stale = services.create_battery(btype, name="Robin").questionnaires.get()
        done = services.create_battery(btype, name="Sky").questionnaires.get()
    submit_metrics_on(done, {"total": 1})

    summary = get(auth_client).json()
    scores = get_scores(auth_client, questionnaireType=scored_type.id).json()

    assert [r["name"] for r in summary["recentSubmissions"]] == ["Sky"]
    assert [r["id"] for r in summary["stalePending"]] == [str(stale.id)]
    assert [r["name"] for r in summary["stalePending"]] == ["Robin"]
    assert [p["name"] for p in metric(scores, "total")["points"]] == ["Sky"]


def submit_metrics_on(q, metrics):
    with freeze_time(NOW):
        return services.submit_questionnaire(q, {}, metrics)
