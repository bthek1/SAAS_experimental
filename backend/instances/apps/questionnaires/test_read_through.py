"""A type used before its event arrives, and what `catalog` being down costs (#13)."""

import uuid

import pytest
from common.peers import PeerUnavailable
from django.utils import timezone
from prometheus_client import REGISTRY

from . import services
from .factories import (
    BatteryTypeFactory,
    QuestionnaireFactory,
    QuestionnaireTypeFactory,
)
from .models import BatteryTypeRef, BatteryTypeRefSlot, QuestionnaireTypeRef, RetiredRef

pytestmark = pytest.mark.django_db

QUESTIONNAIRES = "/api/questionnaires/"
BATTERIES = "/api/batteries/"


class Down:
    def fetch(self, kind, ref_id):  # noqa: ARG002
        raise PeerUnavailable("catalog is down")


class FakeCatalog:
    """What `catalog` would answer. Unknown ids are a 404."""

    types: dict = {}

    def fetch(self, kind, ref_id):  # noqa: ARG002
        return FakeCatalog.types.get(str(ref_id))


def source(owner, kind="questionnaire_type", **data):
    ref_id = str(uuid.uuid4())
    now = timezone.now().isoformat()
    fields = {
        "ownerId": str(owner.pk),
        "title": "Fresh",
        "createdAt": now,
        "updatedAt": now,
    }
    if kind == "questionnaire_type":
        fields["questionnaireJson"] = {"pages": []}
    else:
        fields |= {"description": "", "items": []}
    snapshot = {
        "type": f"{kind}.changed",
        "aggregateId": ref_id,
        "version": 1,
        "data": {**fields, **data},
    }
    FakeCatalog.types[ref_id] = snapshot
    return snapshot


@pytest.fixture(autouse=True)
def catalog(settings):
    settings.CATALOG_CLIENT = f"{__name__}.FakeCatalog"
    FakeCatalog.types = {}
    return FakeCatalog


@pytest.fixture
def catalog_down(settings):
    settings.CATALOG_CLIENT = f"{__name__}.Down"


def test_new_type_is_usable_immediately(auth_client, user):
    fresh = source(user)
    assert not QuestionnaireTypeRef.objects.filter(pk=fresh["aggregateId"]).exists()

    response = auth_client.post(
        QUESTIONNAIRES, {"questionnaireTypeId": fresh["aggregateId"]}, format="json"
    )

    assert response.status_code == 201
    assert response.data["questionnaireType"]["title"] == "Fresh"


def test_new_battery_type_is_usable_immediately(auth_client, user):
    qtype = source(user, title="Slot")
    battery_type = source(
        user,
        kind="battery_type",
        items=[{"questionnaireTypeId": qtype["aggregateId"], "order": 0}],
    )

    response = auth_client.post(
        BATTERIES, {"batteryTypeId": battery_type["aggregateId"]}, format="json"
    )

    assert response.status_code == 201
    assert [q["questionnaireTypeName"] for q in response.data["questionnaires"]] == [
        "Slot"
    ]


def test_store_snapshot_restores_after_failed_delete(auth_client, user):
    """`catalog` crashed after the retire: the type exists, so the owner can use it."""
    fresh = source(user)
    RetiredRef.objects.create(kind="questionnaire_type", ref_id=fresh["aggregateId"])

    response = auth_client.post(
        QUESTIONNAIRES, {"questionnaireTypeId": fresh["aggregateId"]}, format="json"
    )

    assert response.status_code == 201
    assert not RetiredRef.objects.exists()


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
    foreign = source(other_user)
    response = auth_client.post(
        QUESTIONNAIRES, {"questionnaireTypeId": foreign["aggregateId"]}, format="json"
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
    fresh = source(user)
    battery_type = BatteryTypeFactory(owner=user)
    BatteryTypeRefSlot.objects.create(
        battery_type=battery_type,
        questionnaire_type_id=fresh["aggregateId"],
        order=0,
    )

    battery = services.create_battery(battery_type)

    assert (
        str(battery.questionnaires.get().questionnaire_type_id)
        == (fresh["aggregateId"])
    )


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


def test_read_throughs_are_counted_by_result(auth_client, user, settings):
    def count(result):
        return (
            REGISTRY.get_sample_value("app_ref_read_through_total", {"result": result})
            or 0
        )

    found, missing, unavailable = count("found"), count("missing"), count("unavailable")
    fresh = source(user)
    post = lambda ref_id: auth_client.post(  # noqa: E731
        QUESTIONNAIRES, {"questionnaireTypeId": str(ref_id)}, format="json"
    )
    assert post(fresh["aggregateId"]).status_code == 201
    assert post(uuid.uuid4()).status_code == 400
    settings.CATALOG_CLIENT = f"{__name__}.Down"
    assert post(uuid.uuid4()).status_code == 503
    assert count("found") == found + 1
    assert count("missing") == missing + 1
    assert count("unavailable") == unavailable + 1
