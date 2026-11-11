"""The events `catalog` sends have the shapes in backend/contracts/."""

from .contracts import assert_same_shape


def test_questionnaire_type_events(client, owner, stub):  # noqa: ARG001
    created = client.post(
        "/api/questionnaire-types/", json={"title": "Q", "questionnaireJson": {"a": 1}}
    ).json()
    client.delete(f"/api/questionnaire-types/{created['id']}/")
    changed, deleted = stub.events_for(created["id"])
    assert_same_shape(changed, "event.questionnaire_type.changed", "questionnaireJson")
    assert_same_shape(deleted, "event.questionnaire_type.deleted")


def test_battery_type_events(client, owner, stub):  # noqa: ARG001
    qtype = client.post("/api/questionnaire-types/", json={"title": "Q"}).json()
    battery = client.post(
        "/api/battery-types/",
        json={"title": "B", "questionnaireTypeIds": [qtype["id"]]},
    ).json()
    client.delete(f"/api/battery-types/{battery['id']}/")
    changed, deleted = stub.events_for(battery["id"])
    assert_same_shape(changed, "event.battery_type.changed")
    assert_same_shape(deleted, "event.battery_type.deleted")
