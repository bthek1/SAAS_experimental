from datetime import UTC, datetime, timedelta

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings
from freezegun import freeze_time

from . import refs
from .factories import BatteryTypeFactory, QuestionnaireTypeFactory, make_owner
from .models import Battery, Questionnaire, QuestionnaireTypeRef
from .seeding import seed_instances

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db


def seeded_owner():
    """The copies `catalog`'s seed_loadtest creates for one owner."""
    owner = make_owner()
    scales = [
        QuestionnaireTypeFactory(owner=owner, title=f"Scale {i + 1}") for i in range(3)
    ]
    BatteryTypeFactory(
        owner=owner, title="Intake battery", questionnaire_types=scales[:2]
    )
    return owner


def seed(**kwargs):
    options = {"questionnaires_per_owner": 50}
    return seed_instances(**{**options, **kwargs}, now=NOW)


def test_counts_match_the_options():
    first = seeded_owner()
    seeded_owner()
    result = seed()

    assert result.owners_seeded == 2
    assert Questionnaire.objects.count() == result.questionnaires == 100
    assert Battery.objects.count() == result.batteries == 2 * 5
    assert Questionnaire.objects.filter(owner_id=first.pk).count() == 50


def test_second_run_adds_nothing():
    seeded_owner()
    seed()
    again = seed()

    assert again.owners_seeded == 0
    assert again.owners_skipped == 1
    assert Questionnaire.objects.count() == 50


def test_a_new_owner_adds_only_their_rows():
    seeded_owner()
    seed()
    before = set(Questionnaire.objects.values_list("id", flat=True))

    seeded_owner()
    assert seed().owners_seeded == 1
    assert Questionnaire.objects.count() == 100
    assert before <= set(Questionnaire.objects.values_list("id", flat=True))


def test_deterministic():
    owner = seeded_owner()

    def snapshot():
        return list(
            Questionnaire.objects.order_by("name").values_list(
                "name", "questionnaire_type__title", "created_at", "submitted_at"
            )
        )

    seed()
    first = snapshot()
    Questionnaire.objects.filter(owner_id=owner.pk).delete()
    Battery.objects.filter(owner_id=owner.pk).delete()

    seed()
    assert snapshot() == first


def test_spread_over_90_days_and_every_dashboard_window():
    seeded_owner()
    seed()
    rows = Questionnaire.objects.all()

    assert all(NOW - timedelta(days=90) <= q.created_at <= NOW for q in rows)
    submitted = [q for q in rows if q.submitted_at]
    assert 0.5 < len(submitted) / len(rows) < 0.9
    assert all(q.created_at <= q.submitted_at <= NOW for q in submitted)
    for days in (7, 30, 90):
        assert any(q.submitted_at >= NOW - timedelta(days=days) for q in submitted)


def test_submitted_rows_carry_metrics_and_a_snapshot():
    seeded_owner()
    seed()
    submitted = Questionnaire.objects.exclude(submitted_at=None).select_related(
        "questionnaire_type"
    )

    for q in submitted:
        assert set(q.metrics_json) == {"total", "severity", "flag"}
        assert q.questionnaire_json_snapshot == q.questionnaire_type.questionnaire_json
    assert not Questionnaire.objects.filter(submitted_at=None).exclude(metrics_json={})


def test_battery_slots_share_the_battery_date():
    seeded_owner()
    seed()
    for battery in Battery.objects.prefetch_related("questionnaires"):
        slots = battery.questionnaires.all()
        assert sorted(q.battery_order for q in slots) == [0, 1]
        assert {q.created_at for q in slots} == {battery.created_at}


@freeze_time(NOW)
@override_settings(LOADTEST=True)
def test_command(capsys):
    seeded_owner()
    call_command("seed_loadtest", "--questionnaires-per-owner=10")
    assert "owners: 1 seeded" in capsys.readouterr().out
    assert Questionnaire.objects.count() == 10


@override_settings(DEBUG=False)
def test_command_refuses_outside_loadtest_and_debug():
    seeded_owner()
    with pytest.raises(CommandError, match="only under DEBUG or loadtest"):
        call_command("seed_loadtest")
    assert not Questionnaire.objects.exists()


def test_an_owner_without_copies_gets_nothing():
    assert seed().owners_seeded == 0
    assert not QuestionnaireTypeRef.objects.exists()
    assert refs.MODELS  # the module reads only its own tables
