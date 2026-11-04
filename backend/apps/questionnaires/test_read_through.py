"""A type used before its event arrives, and what `catalog` being down costs (#13)."""

import uuid

import pytest

from apps.catalog.factories import BatteryTypeFactory as SourceBatteryTypeFactory
from apps.catalog.factories import QuestionnaireTypeFactory as SourceTypeFactory
from apps.utils.peers import PeerUnavailable

from . import services
from .factories import (
    BatteryTypeFactory,
    QuestionnaireFactory,
    QuestionnaireTypeFactory,
)
from .models import BatteryTypeRef, BatteryTypeRefSlot, QuestionnaireTypeRef

pytestmark = pytest.mark.django_db

QUESTIONNAIRES = "/api/questionnaires/"
BATTERIES = "/api/batteries/"


class Down:
    def fetch(self, kind, ref_id):  # noqa: ARG002
        raise PeerUnavailable("catalog is down")


@pytest.fixture
def catalog_down(settings):
    settings.CATALOG_CLIENT = f"{__name__}.Down"


def test_new_type_is_usable_immediately(auth_client):
    # The API write delivers only after the commit, so no copy exists yet.
    created = auth_client.post(
        "/api/questionnaire-types/", {"title": "Fresh"}, format="json"
    ).data
    assert not QuestionnaireTypeRef.objects.filter(pk=created["id"]).exists()

    response = auth_client.post(
        QUESTIONNAIRES, {"questionnaireTypeId": created["id"]}, format="json"
    )

    assert response.status_code == 201
    assert response.data["questionnaireType"]["title"] == "Fresh"


def test_new_battery_type_is_usable_immediately(auth_client, user):
    qtype = SourceTypeFactory(owner=user)
    source = SourceBatteryTypeFactory(owner=user, questionnaire_types=[qtype])

    response = auth_client.post(BATTERIES, {"batteryTypeId": source.pk}, format="json")

    assert response.status_code == 201
    assert [q["questionnaireTypeName"] for q in response.data["questionnaires"]] == [
        qtype.title
    ]


def test_catalog_down_returns_503_not_400(auth_client, catalog_down):  # noqa: ARG001
    response = auth_client.post(
        QUESTIONNAIRES, {"questionnaireTypeId": str(uuid.uuid4())}, format="json"
    )
    assert response.status_code == 503


def test_unknown_type_is_still_400(auth_client):
    response = auth_client.post(
        QUESTIONNAIRES, {"questionnaireTypeId": str(uuid.uuid4())}, format="json"
    )
    assert response.status_code == 400
    assert "questionnaireTypeId" in response.data


def test_read_through_refuses_another_owners_type(auth_client, other_user):
    foreign = SourceTypeFactory(owner=other_user)
    response = auth_client.post(
        QUESTIONNAIRES, {"questionnaireTypeId": str(foreign.pk)}, format="json"
    )
    assert response.status_code == 400
    assert "questionnaireTypeId" in response.data


def test_known_type_needs_no_catalog(auth_client, qtype, catalog_down):  # noqa: ARG001
    response = auth_client.post(
        QUESTIONNAIRES, {"questionnaireTypeId": str(qtype.pk)}, format="json"
    )
    assert response.status_code == 201


def test_respondent_flow_needs_no_catalog(api_client, qtype, catalog_down):  # noqa: ARG001
    questionnaire = QuestionnaireFactory(questionnaire_type=qtype)
    url = f"{QUESTIONNAIRES}by-token/{questionnaire.share_token}/"
    assert api_client.get(url).status_code == 200
    response = api_client.patch(f"{url}submit/", {"answers": {"q1": 1}}, format="json")
    assert response.status_code == 200
    questionnaire.refresh_from_db()
    assert questionnaire.questionnaire_json_snapshot == qtype.questionnaire_json


def test_battery_slot_copy_is_fetched_when_missing(user):
    qtype = QuestionnaireTypeFactory(owner=user)
    battery_type = BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
    QuestionnaireTypeRef.objects.filter(pk=qtype.pk).delete()

    battery = services.create_battery(battery_type)

    assert battery.questionnaires.get().questionnaire_type_id == qtype.pk


def test_battery_with_an_unfetchable_slot_is_503(auth_client, user, settings):
    qtype = QuestionnaireTypeFactory(owner=user)
    battery_type = BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
    QuestionnaireTypeRef.objects.filter(pk=qtype.pk).delete()
    settings.CATALOG_CLIENT = f"{__name__}.Down"

    response = auth_client.post(
        BATTERIES, {"batteryTypeId": str(battery_type.pk)}, format="json"
    )

    assert response.status_code == 503
    assert BatteryTypeRef.objects.get(pk=battery_type.pk).instances.count() == 0


def test_battery_with_a_slot_catalog_no_longer_has_is_503(auth_client, user):
    battery_type = BatteryTypeFactory(owner=user)
    BatteryTypeRefSlot.objects.create(
        battery_type=battery_type, questionnaire_type_id=uuid.uuid4(), order=0
    )
    response = auth_client.post(
        BATTERIES, {"batteryTypeId": str(battery_type.pk)}, format="json"
    )
    assert response.status_code == 503
