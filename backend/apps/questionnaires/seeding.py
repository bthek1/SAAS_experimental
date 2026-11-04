"""A deterministic, realistic dataset for load tests (#9). See `seed_loadtest`.

Each owner gets scored questionnaire types, a two-slot battery type,
batteries and standalone questionnaires, created over the last 90 days with
about 70 % submitted. That gives the list, dashboard and score endpoints real
work instead of an empty account.

Owners are `loadtest-<n>@example.com`. An owner who already exists is left
as is, so running it twice adds nothing, and raising `--owners` adds only the
new ones.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from . import refs
from .catalog_port import create_owner, owner_email, owner_exists, seed_owner_types
from .models import Battery, BatteryTypeRef, Questionnaire, QuestionnaireTypeRef

SPAN_DAYS = 90
SUBMITTED_SHARE = 0.7
BATTERY_SHARE = 0.2  # of each owner's questionnaires, two per battery
SEVERITIES = ["Minimal", "Mild", "Moderate", "Severe"]


def _response(rng: random.Random) -> tuple[dict, dict]:
    a, b = rng.randint(1, 5), rng.randint(1, 5)
    total = a + b
    metrics = {
        "total": total,
        "severity": SEVERITIES[min((total - 2) // 2, 3)],
        "flag": a > 4,
    }
    return {"a": a, "b": b}, metrics


@dataclass
class SeedResult:
    owners_created: int = 0
    owners_skipped: int = 0
    questionnaire_types: int = 0
    batteries: int = 0
    questionnaires: int = 0
    submitted: int = 0


def seed_loadtest(
    *,
    owners: int,
    questionnaires_per_owner: int,
    password: str,
    seed: int = 1234,
    now: datetime | None = None,
) -> SeedResult:
    now = now or timezone.now()
    result = SeedResult()
    for n in range(owners):
        email = owner_email(n)
        if owner_exists(email):
            result.owners_skipped += 1
            continue
        # One generator per owner, so adding owners never changes earlier ones.
        rng = random.Random(f"{seed}-{n}")  # noqa: S311 - test data, not security
        with transaction.atomic():
            owner = create_owner(email, password)
            _seed_owner(owner, questionnaires_per_owner, rng, now, result)
        result.owners_created += 1
    return result


def _seed_owner(owner, count, rng, now, result) -> None:
    # The copies are written directly: delivery only happens after the commit.
    sources, battery_source = seed_owner_types(owner)
    for source in [*sources, battery_source]:
        refs.store_snapshot(source)
    types = list(
        QuestionnaireTypeRef.objects.filter(
            pk__in=[UUID(source["aggregateId"]) for source in sources]
        ).order_by("title")
    )
    battery_type = BatteryTypeRef.objects.get(pk=UUID(battery_source["aggregateId"]))

    def created_at() -> datetime:
        return now - timedelta(seconds=rng.uniform(0, SPAN_DAYS * 86400))

    batteries = Battery.objects.bulk_create(
        Battery(owner_id=owner.pk, battery_type=battery_type, name=f"Battery {i + 1}")
        for i in range(int(count * BATTERY_SHARE) // 2)
    )
    rows = [
        Questionnaire(
            owner_id=owner.pk,
            questionnaire_type=qt,
            battery=battery,
            battery_order=order,
            name=f"Respondent {i + 1}",
        )
        for i, battery in enumerate(batteries)
        for order, qt in enumerate(types[:2])
    ]
    rows += [
        Questionnaire(
            owner_id=owner.pk,
            questionnaire_type=rng.choice(types),
            name=f"Respondent {len(batteries) + i + 1}",
        )
        for i in range(count - len(rows))
    ]

    battery_created = {battery.pk: created_at() for battery in batteries}
    row_created = [battery_created.get(q.battery_id) or created_at() for q in rows]
    for q, created in zip(rows, row_created, strict=True):
        if rng.random() < SUBMITTED_SHARE:
            submitted = created + timedelta(hours=rng.uniform(0.5, 72))
            q.submitted_at = min(submitted, now)
            q.answers_json, q.metrics_json = _response(rng)
            q.questionnaire_json_snapshot = q.questionnaire_type.questionnaire_json
    Questionnaire.objects.bulk_create(rows, batch_size=1000)

    # auto_now_add stamps created_at on insert, so backdate with an update.
    for q, created in zip(rows, row_created, strict=True):
        q.created_at = created
    for battery in batteries:
        battery.created_at = battery_created[battery.pk]
    Questionnaire.objects.bulk_update(rows, ["created_at"], batch_size=1000)
    Battery.objects.bulk_update(batteries, ["created_at"])

    result.questionnaire_types += len(types)
    result.batteries += len(batteries)
    result.questionnaires += len(rows)
    result.submitted += sum(q.submitted_at is not None for q in rows)
