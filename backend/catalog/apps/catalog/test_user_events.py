"""User changes reach `instances` as events (#13)."""

import pytest

from .models import OutboxEvent

pytestmark = pytest.mark.django_db


def events_for(user_id):
    return list(
        OutboxEvent.objects.filter(aggregate_id=user_id)
        .order_by("version")
        .values_list("event_type", flat=True)
    )


def test_deactivating_and_reactivating_are_published_in_order(user):
    user.is_active = False
    user.save()
    user.is_active = True
    user.save()
    assert events_for(user.pk) == ["user.deactivated", "user.reactivated"]


def test_saving_a_user_without_a_change_emits_nothing(user):
    user.first_name = "New"
    user.save()
    assert events_for(user.pk) == []


def test_saving_other_fields_only_emits_nothing(user):
    user.is_active = False
    user.save(update_fields=["first_name"])
    assert events_for(user.pk) == []


def test_deleting_is_published(user):
    user_id = user.pk
    user.delete()
    assert events_for(user_id) == ["user.deleted"]
