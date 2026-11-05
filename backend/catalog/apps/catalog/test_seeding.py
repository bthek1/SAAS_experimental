from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import override_settings

from .models import BatteryType, OutboxEvent, QuestionnaireType
from .seeding import owner_email, seed_catalog

pytestmark = pytest.mark.django_db


def seed(**kwargs):
    return seed_catalog(**{"owners": 2, "password": "pw-12345", **kwargs})


def test_counts_match_the_options():
    result = seed()

    assert result.owners_created == 2
    assert get_user_model().objects.filter(email__startswith="loadtest-").count() == 2
    assert QuestionnaireType.objects.count() == result.questionnaire_types == 6
    assert BatteryType.objects.count() == 2
    assert get_user_model().objects.get(email=owner_email(0)).check_password("pw-12345")


def test_every_type_is_published():
    seed(owners=1)
    assert (
        list(
            OutboxEvent.objects.order_by("event_type").values_list(
                "event_type", flat=True
            )
        )
        == ["battery_type.changed"] + ["questionnaire_type.changed"] * 3
    )
    assert all(event.version == 1 for event in OutboxEvent.objects.all())


def test_second_run_adds_nothing():
    seed()
    again = seed()
    assert again.owners_created == 0
    assert again.owners_skipped == 2
    assert QuestionnaireType.objects.count() == 6


def test_ids_are_the_same_on_every_run():
    def ids():
        return sorted(QuestionnaireType.objects.values_list("id", flat=True))

    seed()
    first = ids()
    get_user_model().objects.all().delete()
    seed()
    assert ids() == first


@override_settings(LOADTEST=True)
def test_command(capsys):
    call_command("seed_loadtest", "--owners=1", "--password=pw")
    assert "owners: 1 created" in capsys.readouterr().out


@override_settings(DEBUG=False)
def test_command_refuses_outside_loadtest_and_debug():
    with pytest.raises(CommandError, match="only under DEBUG or loadtest"):
        call_command("seed_loadtest", "--password=pw")
    assert not get_user_model().objects.exists()


@override_settings(LOADTEST=True)
def test_command_needs_a_password():
    with (
        patch.dict("os.environ", clear=False),
        pytest.raises(CommandError, match="LOADTEST_OWNER_PASSWORD"),
    ):
        call_command("seed_loadtest", "--password=")
