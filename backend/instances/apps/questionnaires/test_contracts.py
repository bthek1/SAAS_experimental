"""`instances` accepts exactly what backend/contracts/ says `catalog` sends (#13)."""

import json
import uuid
from pathlib import Path

import pytest

from .catalog_client import HttpCatalog
from .models import (
    BatteryTypeRef,
    BlockedOwner,
    QuestionnaireTypeRef,
    RetiredRef,
)

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
OWNER = uuid.UUID("11111111-1111-1111-1111-111111111111")
QT = uuid.UUID("22222222-2222-2222-2222-222222222222")
BT = uuid.UUID("33333333-3333-3333-3333-333333333333")
pytestmark = pytest.mark.django_db


def contract(name: str) -> dict:
    return json.loads((CONTRACTS / f"{name}.json").read_text())


def send(client, name: str):
    return client.post("/internal/events/", contract(name), format="json")


def test_questionnaire_type_changed(internal_client):
    response = send(internal_client, "event.questionnaire_type.changed")
    assert response.status_code == 200
    assert response.json() == {"result": "applied"}
    ref = QuestionnaireTypeRef.objects.get(pk=QT)
    assert (ref.owner_id, ref.title) == (OWNER, "PHQ-9")
    assert ref.updated_at.isoformat() == "2026-01-02T03:04:05.123456+00:00"


def test_battery_type_changed(internal_client):
    assert send(internal_client, "event.battery_type.changed").status_code == 200
    slot = BatteryTypeRef.objects.get(pk=BT).slots.get()
    assert (slot.questionnaire_type_id, slot.order) == (QT, 0)


@pytest.mark.parametrize(
    ("changed", "deleted", "model", "ref_id"),
    [
        ("questionnaire_type", "questionnaire_type", QuestionnaireTypeRef, QT),
        ("battery_type", "battery_type", BatteryTypeRef, BT),
    ],
)
def test_type_deleted(internal_client, changed, deleted, model, ref_id):
    send(internal_client, f"event.{changed}.changed")
    assert send(internal_client, f"event.{deleted}.deleted").status_code == 200
    assert not model.objects.filter(pk=ref_id).exists()
    assert RetiredRef.objects.filter(ref_id=ref_id).exists()


def test_user_events(internal_client):
    assert send(internal_client, "event.user.deactivated").status_code == 200
    assert BlockedOwner.objects.get(pk=OWNER).blocked
    assert send(internal_client, "event.user.reactivated").status_code == 200
    assert not BlockedOwner.objects.get(pk=OWNER).blocked
    assert send(internal_client, "event.user.deleted").status_code == 200
    assert BlockedOwner.objects.get(pk=OWNER).deleted


@pytest.mark.parametrize(
    ("kind", "name", "ref_id"),
    [
        ("questionnaire_type", "response.questionnaire_type", QT),
        ("battery_type", "response.battery_type", BT),
    ],
)
def test_client_reads_a_snapshot_response(mocker, kind, name, ref_id):
    mocker.patch(
        "apps.questionnaires.catalog_client.peer_request",
        return_value=mocker.Mock(status_code=200, json=lambda: contract(name)),
    )
    snapshot = HttpCatalog().fetch(kind, ref_id)
    assert snapshot["aggregateId"] == str(ref_id)


def test_client_walks_a_page_response(mocker):
    mocker.patch(
        "apps.questionnaires.catalog_client.peer_request",
        return_value=mocker.Mock(
            status_code=200, json=lambda: contract("response.type_page")
        ),
    )
    rows = list(HttpCatalog().iter_snapshots("questionnaire_type"))
    assert [row["aggregateId"] for row in rows] == [str(QT)]
