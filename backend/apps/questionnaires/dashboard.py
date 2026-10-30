"""Owner-scoped aggregates for the dashboard.

A window of `days` starts at UTC midnight `days - 1` days ago, so "7" is today plus the
six days before it. `None` means all time.

Questionnaire KPIs and per-type counts follow a cohort: the questionnaires
*created* in the window, and how many of those have been submitted (whenever
that happened). This keeps the completion rate within 0-100%. Activity
(`submissionsByDay`, `recentSubmissions`) counts by `submitted_at` instead.
Pending items older than STALE_AFTER are listed whatever the window, since they
need following up.
"""

from datetime import datetime, timedelta
from statistics import median
from typing import Any

from django.db.models import Count, Q, QuerySet, Value
from django.db.models.functions import Coalesce, NullIf, TruncDate
from django.utils import timezone

from .models import (
    Battery,
    BatteryType,
    BatteryTypeItem,
    Questionnaire,
    QuestionnaireType,
)

STALE_AFTER = timedelta(days=7)
LIST_LIMIT = 10

# Questionnaires created by a battery have no name of their own; show the battery's.
RESPONDENT = Coalesce(NullIf("name", Value("")), "battery__name", Value(""))


def window_start(days: int | None, now: datetime) -> datetime | None:
    if days is None:
        return None
    first_day = now.date() - timedelta(days=days - 1)
    return datetime.combine(first_day, datetime.min.time(), tzinfo=now.tzinfo)


def _battery_status(total: int, submitted: int) -> str:
    if total > 0 and submitted == total:
        return "complete"
    if submitted == 0:
        return "notStarted"
    return "inProgress"


def _submissions_by_day(
    submitted: QuerySet[Questionnaire], start: datetime | None, now: datetime
) -> list[dict[str, Any]]:
    counts = dict(
        submitted.annotate(day=TruncDate("submitted_at"))
        .values("day")
        .annotate(count=Count("id"))
        .values_list("day", "count")
    )
    if not counts and start is None:
        return []
    day = start.date() if start is not None else min(counts)
    series = []
    while day <= now.date():
        series.append({"date": day, "count": counts.get(day, 0)})
        day += timedelta(days=1)
    return series


def dashboard_summary(
    owner, days: int | None = None, questionnaire_type: QuestionnaireType | None = None
) -> dict[str, Any]:
    now = timezone.now()
    start = window_start(days, now)

    questionnaires = Questionnaire.objects.filter(owner=owner)
    batteries = Battery.objects.filter(owner=owner)
    qtypes = QuestionnaireType.objects.filter(owner=owner)
    btypes = BatteryType.objects.filter(owner=owner)
    if questionnaire_type is not None:
        questionnaires = questionnaires.filter(questionnaire_type=questionnaire_type)
        # A subquery rather than a join, so the slot counts below still see every
        # questionnaire in the battery, not just the ones of this type.
        batteries = batteries.filter(
            pk__in=Questionnaire.objects.filter(
                questionnaire_type=questionnaire_type
            ).values("battery_id")
        )
        qtypes = qtypes.filter(pk=questionnaire_type.pk)
        btypes = btypes.filter(
            pk__in=BatteryTypeItem.objects.filter(
                questionnaire_type=questionnaire_type
            ).values("battery_type_id")
        )

    cohort = questionnaires
    submitted_in_window = questionnaires.exclude(submitted_at=None)
    if start is not None:
        cohort = cohort.filter(created_at__gte=start)
        submitted_in_window = submitted_in_window.filter(submitted_at__gte=start)
        batteries = batteries.filter(created_at__gte=start)

    counts = cohort.aggregate(
        sent=Count("id"), submitted=Count("id", filter=~Q(submitted_at=None))
    )
    durations = [
        (submitted_at - created_at).total_seconds() / 3600
        for created_at, submitted_at in cohort.exclude(submitted_at=None).values_list(
            "created_at", "submitted_at"
        )
    ]

    in_cohort = Q(instances__owner=owner)
    if start is not None:
        in_cohort &= Q(instances__created_at__gte=start)
    by_qtype = (
        qtypes.annotate(
            sent=Count("instances", filter=in_cohort),
            submitted=Count(
                "instances", filter=in_cohort & ~Q(instances__submitted_at=None)
            ),
        )
        .order_by("title")
        .values("id", "title", "sent", "submitted")
    )

    battery_rows = batteries.annotate(
        total=Count("questionnaires", distinct=True),
        submitted=Count(
            "questionnaires",
            filter=~Q(questionnaires__submitted_at=None),
            distinct=True,
        ),
    ).values_list("battery_type_id", "total", "submitted")
    status_by_btype: dict[Any, dict[str, int]] = {}
    battery_kpis = {"complete": 0, "inProgress": 0, "notStarted": 0}
    for btype_id, total, submitted in battery_rows:
        status = _battery_status(total, submitted)
        battery_kpis[status] += 1
        bucket = status_by_btype.setdefault(
            btype_id, {"complete": 0, "inProgress": 0, "notStarted": 0}
        )
        bucket[status] += 1

    recent = (
        submitted_in_window.annotate(respondent=RESPONDENT)
        .order_by("-submitted_at")
        .values("id", "respondent", "questionnaire_type__title", "submitted_at")[
            :LIST_LIMIT
        ]
    )
    stale = (
        questionnaires.filter(submitted_at=None, created_at__lt=now - STALE_AFTER)
        .annotate(respondent=RESPONDENT)
        .order_by("created_at")
        .values(
            "id", "respondent", "questionnaire_type__title", "share_token", "created_at"
        )[:LIST_LIMIT]
    )

    return {
        "range": {"days": days, "from": start, "to": now},
        "kpis": {
            "questionnairesSent": counts["sent"],
            "questionnairesSubmitted": counts["submitted"],
            "questionnairesPending": counts["sent"] - counts["submitted"],
            "completionRate": (
                round(counts["submitted"] / counts["sent"], 4)
                if counts["sent"]
                else 0.0
            ),
            "medianHoursToComplete": round(median(durations), 1) if durations else None,
            "batteriesTotal": sum(battery_kpis.values()),
            "batteriesComplete": battery_kpis["complete"],
            "batteriesInProgress": battery_kpis["inProgress"],
            "batteriesNotStarted": battery_kpis["notStarted"],
        },
        "submissionsByDay": _submissions_by_day(submitted_in_window, start, now),
        "byQuestionnaireType": [
            {**t, "pending": t["sent"] - t["submitted"]} for t in by_qtype
        ],
        "byBatteryType": [
            {
                "id": bt.id,
                "title": bt.title,
                **status_by_btype.get(
                    bt.id, {"complete": 0, "inProgress": 0, "notStarted": 0}
                ),
            }
            for bt in btypes.order_by("title")
        ],
        "recentSubmissions": [
            {
                "id": q["id"],
                "name": q["respondent"],
                "questionnaireTypeTitle": q["questionnaire_type__title"],
                "submittedAt": q["submitted_at"],
            }
            for q in recent
        ],
        "stalePending": [
            {
                "id": q["id"],
                "name": q["respondent"],
                "questionnaireTypeTitle": q["questionnaire_type__title"],
                "shareToken": q["share_token"],
                "createdAt": q["created_at"],
                "ageDays": (now - q["created_at"]).days,
            }
            for q in stale
        ],
    }


def _metric_kind(value: Any) -> str | None:
    # bool before int: True is an int in Python.
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "numeric"
    if isinstance(value, str):
        return "categorical"
    return None


def _metric_labels(questionnaire_json: dict) -> dict[str, str]:
    """`calculatedValues` names to display labels, in definition order."""
    labels: dict[str, str] = {}
    for definition in questionnaire_json.get("calculatedValues") or []:
        if isinstance(definition, dict) and isinstance(definition.get("name"), str):
            labels[definition["name"]] = str(
                definition.get("title") or definition["name"]
            )
    return labels


def dashboard_scores(
    owner, questionnaire_type: QuestionnaireType, days: int | None = None
) -> dict[str, Any]:
    """Every stored metric of one type's submitted questionnaires, by metric.

    A metric's kind comes from its first value (number, string or bool); later
    values of another kind are skipped. Labels and order follow the type's current
    `calculatedValues`, then any names that only older snapshots had.
    """
    start = window_start(days, timezone.now())
    rows = Questionnaire.objects.filter(
        owner=owner, questionnaire_type=questionnaire_type
    ).exclude(submitted_at=None)
    if start is not None:
        rows = rows.filter(submitted_at__gte=start)

    labels = _metric_labels(questionnaire_type.questionnaire_json)
    metrics: dict[str, dict[str, Any]] = {}
    points = (
        rows.annotate(respondent=RESPONDENT)
        .order_by("submitted_at")
        .values_list("id", "respondent", "submitted_at", "metrics_json")
    )
    for qid, name, submitted_at, stored in points:
        for metric, value in (stored or {}).items():
            kind = _metric_kind(value)
            if kind is None:
                continue
            entry = metrics.setdefault(
                metric,
                {
                    "name": metric,
                    "label": labels.get(metric, metric),
                    "kind": kind,
                    "points": [],
                },
            )
            if entry["kind"] != kind:
                continue
            entry["points"].append(
                {
                    "questionnaireId": qid,
                    "name": name,
                    "submittedAt": submitted_at,
                    "value": value,
                }
            )

    for entry in metrics.values():
        values = [p["value"] for p in entry["points"]]
        if entry["kind"] == "numeric":
            entry["mean"] = round(sum(values) / len(values), 2)
        else:
            counts: dict[Any, int] = {}
            for value in values:
                counts[value] = counts.get(value, 0) + 1
            entry["distribution"] = [
                {"value": value, "count": count}
                for value, count in sorted(
                    counts.items(), key=lambda item: (-item[1], str(item[0]))
                )
            ]

    order = list(labels)
    ordered = sorted(
        metrics.values(),
        key=lambda m: (
            order.index(m["name"]) if m["name"] in order else len(order),
            m["name"],
        ),
    )
    return {"questionnaireTypeId": questionnaire_type.id, "metrics": ordered}
