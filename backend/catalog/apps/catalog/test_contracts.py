"""`catalog` produces exactly the shapes in backend/contracts/ (#13)."""

import json
from pathlib import Path

import pytest

from . import events
from .factories import BatteryTypeFactory, QuestionnaireTypeFactory
from .models import OutboxEvent

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
pytestmark = pytest.mark.django_db


def contract(name: str) -> dict:
    return json.loads((CONTRACTS / f"{name}.json").read_text())


def shape(value):
    """Keys and value types. A `{}` or `[]` says nothing about what it can hold."""
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


def assert_same_shape(actual: dict, name: str, *opaque: str) -> None:
    expected = contract(name)
    actual_data, expected_data = dict(actual["data"]), dict(expected["data"])
    for key in opaque:  # free-form JSON owned by the type's author
        actual_data.pop(key), expected_data.pop(key)
    assert shape({**actual, "data": actual_data}) == shape(
        {**expected, "data": expected_data}
    )


def last_event(event_type: str) -> dict:
    return OutboxEvent.objects.filter(event_type=event_type).latest("created_at")


def test_questionnaire_type_changed(user):
    qtype = QuestionnaireTypeFactory(owner=user)
    events.record_change(qtype)
    event = last_event("questionnaire_type.changed").envelope()
    assert_same_shape(event, "event.questionnaire_type.changed", "questionnaireJson")


def test_battery_type_changed(user):
    qtype = QuestionnaireTypeFactory(owner=user)
    battery_type = BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
    events.record_change(battery_type)
    assert_same_shape(
        last_event("battery_type.changed").envelope(), "event.battery_type.changed"
    )


@pytest.mark.parametrize(
    ("factory", "name"),
    [
        (QuestionnaireTypeFactory, "questionnaire_type.deleted"),
        (BatteryTypeFactory, "battery_type.deleted"),
    ],
)
def test_type_deleted(user, factory, name):
    events.record_deleted(factory(owner=user))
    assert_same_shape(last_event(name).envelope(), f"event.{name}")


def test_user_events(user):
    user.is_active = False
    user.save()
    user.is_active = True
    user.save()
    for name in ("user.deactivated", "user.reactivated"):
        assert_same_shape(last_event(name).envelope(), f"event.{name}")
    user.delete()
    assert_same_shape(last_event("user.deleted").envelope(), "event.user.deleted")


def test_snapshot_responses(user, internal_client):
    qtype = QuestionnaireTypeFactory(owner=user)
    battery_type = BatteryTypeFactory(owner=user, questionnaire_types=[qtype])

    response = internal_client.get(f"/internal/questionnaire-types/{qtype.pk}/")
    assert_same_shape(
        response.json(), "response.questionnaire_type", "questionnaireJson"
    )
    response = internal_client.get(f"/internal/battery-types/{battery_type.pk}/")
    assert_same_shape(response.json(), "response.battery_type")

    page = internal_client.get("/internal/questionnaire-types/").json()
    assert set(page) == set(contract("response.type_page"))
    expected = contract("response.type_page")["results"][0]
    assert set(page["results"][0]) == set(expected)
