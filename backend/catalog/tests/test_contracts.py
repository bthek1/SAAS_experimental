"""This service produces exactly the shapes in backend/contracts/ (#13)."""

import json
from pathlib import Path

import pytest

from catalog import events
from catalog.models import BatteryType, QuestionnaireType
from catalog.services import save_type

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"


def contract(name: str) -> dict:
    return json.loads((CONTRACTS / f"{name}.json").read_text())


def shape(value):
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


def assert_same_shape(actual: dict, name: str, *opaque: str) -> None:
    expected = contract(name)
    actual_data, expected_data = dict(actual["data"]), dict(expected["data"])
    for key in opaque:
        actual_data.pop(key), expected_data.pop(key)
    assert shape({**actual, "data": actual_data}) == shape(
        {**expected, "data": expected_data}
    )


@pytest.fixture
def types(session, user):
    qtype = save_type(
        session,
        QuestionnaireType(owner_id=user.id, title="Q", questionnaire_json={"a": 1}),
        owner_id=user.id,
    )
    battery = save_type(
        session,
        BatteryType(owner_id=user.id, title="B"),
        owner_id=user.id,
        item_ids=[qtype.id],
    )
    return qtype, battery


def test_changed_events(instances, types):
    qtype_event, battery_event = instances.events
    assert_same_shape(
        qtype_event, "event.questionnaire_type.changed", "questionnaireJson"
    )
    assert_same_shape(battery_event, "event.battery_type.changed")


def test_deleted_events(session, types):
    for instance, name in zip(
        types, ("questionnaire_type.deleted", "battery_type.deleted"), strict=True
    ):
        event = events.record_deleted(session, instance)
        assert_same_shape(event.envelope(), f"event.{name}")
    session.rollback()


def test_snapshots(session, types):
    qtype, battery = types
    assert_same_shape(
        events.fetch_snapshot(session, "questionnaire_type", qtype.id),
        "response.questionnaire_type",
        "questionnaireJson",
    )
    assert_same_shape(
        events.fetch_snapshot(session, "battery_type", battery.id),
        "response.battery_type",
    )
