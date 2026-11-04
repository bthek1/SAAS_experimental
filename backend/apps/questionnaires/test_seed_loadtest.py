from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import override_settings
from freezegun import freeze_time

from apps.catalog.models import QuestionnaireType

from .catalog_port import owner_email
from .models import Battery, Questionnaire
from .seeding import seed_loadtest

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db


def seed(**kwargs):
    options = {"owners": 2, "questionnaires_per_owner": 50, "password": "pw-12345"}
    return seed_loadtest(**{**options, **kwargs}, now=NOW)


def test_counts_match_the_options():
    result = seed()

    assert result.owners_created == 2
    assert get_user_model().objects.filter(email__startswith="loadtest-").count() == 2
    assert QuestionnaireType.objects.count() == result.questionnaire_types == 6
    assert Questionnaire.objects.count() == result.questionnaires == 100
    assert Battery.objects.count() == result.batteries == 2 * 5
    owner = get_user_model().objects.get(email=owner_email(0))
    assert Questionnaire.objects.filter(owner_id=owner.pk).count() == 50
    assert owner.check_password("pw-12345")


def test_second_run_adds_nothing():
    seed()
    again = seed()

    assert again.owners_created == 0
    assert again.owners_skipped == 2
    assert Questionnaire.objects.count() == 100


def test_more_owners_adds_only_the_new_ones():
    seed()
    before = list(Questionnaire.objects.order_by("id").values_list("id", flat=True))

    assert seed(owners=3).owners_created == 1
    assert Questionnaire.objects.count() == 150
    assert set(before) <= set(Questionnaire.objects.values_list("id", flat=True))


def test_deterministic(django_capture_on_commit_callbacks):
    def snapshot():
        return list(
            Questionnaire.objects.order_by("name").values_list(
                "name", "questionnaire_type__title", "created_at", "submitted_at"
            )
        )

    seed(owners=1)
    first = snapshot()
    with django_capture_on_commit_callbacks(execute=True):
        get_user_model().objects.all().delete()

    seed(owners=1)
    assert snapshot() == first


def test_spread_over_90_days_and_every_dashboard_window():
    seed()
    rows = Questionnaire.objects.all()

    assert all(NOW - timedelta(days=90) <= q.created_at <= NOW for q in rows)
    submitted = [q for q in rows if q.submitted_at]
    assert 0.5 < len(submitted) / len(rows) < 0.9
    assert all(q.created_at <= q.submitted_at <= NOW for q in submitted)
    for days in (7, 30, 90):
        assert any(q.submitted_at >= NOW - timedelta(days=days) for q in submitted)


def test_submitted_rows_carry_metrics_and_a_snapshot():
    seed()
    submitted = Questionnaire.objects.exclude(submitted_at=None).select_related(
        "questionnaire_type"
    )

    for q in submitted:
        assert set(q.metrics_json) == {"total", "severity", "flag"}
        assert q.questionnaire_json_snapshot == q.questionnaire_type.questionnaire_json
    assert not Questionnaire.objects.filter(submitted_at=None).exclude(metrics_json={})


def test_battery_slots_share_the_battery_date():
    seed()
    for battery in Battery.objects.prefetch_related("questionnaires"):
        slots = battery.questionnaires.all()
        assert sorted(q.battery_order for q in slots) == [0, 1]
        assert {q.created_at for q in slots} == {battery.created_at}


@freeze_time(NOW)
@override_settings(LOADTEST=True)
def test_command(capsys):
    call_command(
        "seed_loadtest", "--owners=1", "--questionnaires-per-owner=10", "--password=pw"
    )
    assert "owners: 1 created" in capsys.readouterr().out
    assert Questionnaire.objects.count() == 10


@override_settings(DEBUG=False)
def test_command_refuses_outside_loadtest_and_debug():
    with pytest.raises(CommandError, match="only under DEBUG or loadtest"):
        call_command("seed_loadtest", "--password=pw")
    assert not get_user_model().objects.exists()


@override_settings(LOADTEST=True)
def test_command_needs_a_password(monkeypatch):
    monkeypatch.delenv("LOADTEST_OWNER_PASSWORD", raising=False)
    with pytest.raises(CommandError, match="LOADTEST_OWNER_PASSWORD"):
        call_command("seed_loadtest", "--password=")
