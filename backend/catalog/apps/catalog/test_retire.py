"""Deleting a type asks `instances` first, and fails closed (#13)."""

import pytest
from common.peers import PeerUnavailable, RefInUse
from rest_framework.test import APIClient

from .factories import BatteryTypeFactory, QuestionnaireTypeFactory
from .models import BatteryType, OutboxEvent, QuestionnaireType

pytestmark = pytest.mark.django_db

TYPES = "/api/questionnaire-types/"
BATTERY_TYPES = "/api/battery-types/"


class FakeInstances:
    """Records what `catalog` asked, and answers as told."""

    retired: list = []
    raises: Exception | None = None

    def send_event(self, event):
        pass

    def retire(self, kind, ref_id):
        if FakeInstances.raises is not None:
            raise FakeInstances.raises
        FakeInstances.retired.append((kind, ref_id))


@pytest.fixture(autouse=True)
def instances(settings):
    settings.INSTANCES_CLIENT = f"{__name__}.FakeInstances"
    FakeInstances.retired = []
    FakeInstances.raises = None
    return FakeInstances


def test_delete_in_use_returns_409(auth_client, user, instances):
    qtype = QuestionnaireTypeFactory(owner=user)
    instances.raises = RefInUse()

    assert auth_client.delete(f"{TYPES}{qtype.pk}/").status_code == 409
    assert QuestionnaireType.objects.filter(pk=qtype.pk).exists()


def test_delete_battery_type_in_use_returns_409(auth_client, user, instances):
    battery_type = BatteryTypeFactory(owner=user)
    instances.raises = RefInUse()

    assert auth_client.delete(f"{BATTERY_TYPES}{battery_type.pk}/").status_code == 409
    assert BatteryType.objects.filter(pk=battery_type.pk).exists()


def test_type_in_a_battery_type_is_refused_before_asking_instances(
    auth_client, user, instances
):
    qtype = QuestionnaireTypeFactory(owner=user)
    BatteryTypeFactory(owner=user, questionnaire_types=[qtype])

    assert auth_client.delete(f"{TYPES}{qtype.pk}/").status_code == 409
    assert instances.retired == []


def test_delete_unused_removes_copy_and_type(auth_client, user, instances):
    qtype = QuestionnaireTypeFactory(owner=user)
    type_id = qtype.pk

    assert auth_client.delete(f"{TYPES}{qtype.pk}/").status_code == 204
    assert instances.retired == [("questionnaire_type", type_id)]
    assert not QuestionnaireType.objects.filter(pk=type_id).exists()
    assert OutboxEvent.objects.filter(
        event_type="questionnaire_type.deleted", aggregate_id=type_id
    ).exists()


def test_delete_fails_closed_with_503(auth_client, user, instances):
    qtype = QuestionnaireTypeFactory(owner=user)
    instances.raises = PeerUnavailable("instances is down")

    response = auth_client.delete(f"{TYPES}{qtype.pk}/")

    assert response.status_code == 503
    assert response.data["detail"].code == "service_unavailable"
    assert QuestionnaireType.objects.filter(pk=qtype.pk).exists()


def test_type_survives_a_crash_after_the_retire(user, mocker, instances):
    """The other half is `test_store_snapshot_restores_after_failed_delete`."""
    qtype = QuestionnaireTypeFactory(owner=user)
    mocker.patch.object(QuestionnaireType, "delete", side_effect=RuntimeError("crash"))
    client = APIClient(raise_request_exception=False)
    client.force_authenticate(user)

    assert client.delete(f"{TYPES}{qtype.pk}/").status_code == 500
    assert instances.retired == [("questionnaire_type", qtype.pk)]
    assert QuestionnaireType.objects.filter(pk=qtype.pk).exists()
    assert not OutboxEvent.objects.filter(
        event_type="questionnaire_type.deleted"
    ).exists()
