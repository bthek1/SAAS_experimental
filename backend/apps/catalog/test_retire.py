"""Deleting a type asks `instances` first, and fails closed (#13)."""

import pytest
from rest_framework.test import APIClient

from apps.questionnaires import services
from apps.questionnaires.factories import (
    BatteryTypeFactory,
    QuestionnaireFactory,
    QuestionnaireTypeFactory,
)
from apps.questionnaires.models import QuestionnaireTypeRef, RetiredRef
from apps.utils.peers import PeerUnavailable

from .models import BatteryType, OutboxEvent, QuestionnaireType

pytestmark = pytest.mark.django_db

TYPES = "/api/questionnaire-types/"
BATTERY_TYPES = "/api/battery-types/"
QUESTIONNAIRES = "/api/questionnaires/"


class Down:
    def retire(self, kind, ref_id):  # noqa: ARG002
        raise PeerUnavailable("instances is down")


def test_delete_in_use_returns_409(auth_client, user):
    qtype = QuestionnaireTypeFactory(owner=user)
    QuestionnaireFactory(questionnaire_type=qtype)

    assert auth_client.delete(f"{TYPES}{qtype.pk}/").status_code == 409
    assert QuestionnaireType.objects.filter(pk=qtype.pk).exists()
    assert QuestionnaireTypeRef.objects.filter(pk=qtype.pk).exists()
    # Refused by the RESTRICT, so no tombstone blocks this type's next event.
    assert not RetiredRef.objects.exists()


def test_delete_battery_type_in_use_returns_409(auth_client, user):
    battery_type = BatteryTypeFactory(owner=user)
    services.create_battery(battery_type)
    assert auth_client.delete(f"{BATTERY_TYPES}{battery_type.pk}/").status_code == 409
    assert BatteryType.objects.filter(pk=battery_type.pk).exists()


def test_type_in_a_battery_type_is_refused_before_asking_instances(
    auth_client, user, settings
):
    qtype = QuestionnaireTypeFactory(owner=user)
    BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
    settings.INSTANCES_CLIENT = f"{__name__}.Down"
    assert auth_client.delete(f"{TYPES}{qtype.pk}/").status_code == 409


def test_delete_unused_removes_copy_and_type(auth_client, user):
    qtype = QuestionnaireTypeFactory(owner=user)

    assert auth_client.delete(f"{TYPES}{qtype.pk}/").status_code == 204
    assert not QuestionnaireType.objects.filter(pk=qtype.pk).exists()
    assert not QuestionnaireTypeRef.objects.filter(pk=qtype.pk).exists()
    assert RetiredRef.objects.filter(ref_id=qtype.pk).exists()
    assert OutboxEvent.objects.filter(
        event_type="questionnaire_type.deleted", aggregate_id=qtype.pk
    ).exists()


def test_delete_fails_closed_with_503(auth_client, user, settings):
    qtype = QuestionnaireTypeFactory(owner=user)
    settings.INSTANCES_CLIENT = f"{__name__}.Down"

    response = auth_client.delete(f"{TYPES}{qtype.pk}/")

    assert response.status_code == 503
    assert response.data["detail"].code == "service_unavailable"
    assert QuestionnaireType.objects.filter(pk=qtype.pk).exists()


def test_read_through_restores_after_failed_delete(user, mocker):
    qtype = QuestionnaireTypeFactory(owner=user)
    # The retire succeeds, then catalog dies before its own delete.
    mocker.patch.object(QuestionnaireType, "delete", side_effect=RuntimeError("crash"))
    crashing = APIClient(raise_request_exception=False)
    crashing.force_authenticate(user)
    assert crashing.delete(f"{TYPES}{qtype.pk}/").status_code == 500
    assert not QuestionnaireTypeRef.objects.filter(pk=qtype.pk).exists()
    assert RetiredRef.objects.filter(ref_id=qtype.pk).exists()

    # The type still exists, so the owner can still use it.
    client = APIClient()
    client.force_authenticate(user)
    response = client.post(
        QUESTIONNAIRES, {"questionnaireTypeId": str(qtype.pk)}, format="json"
    )

    assert response.status_code == 201
    assert QuestionnaireTypeRef.objects.filter(pk=qtype.pk).exists()
    assert not RetiredRef.objects.filter(ref_id=qtype.pk).exists()
