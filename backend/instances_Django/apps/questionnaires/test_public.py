import uuid

import pytest

from . import services
from .factories import (
    BatteryTypeFactory,
    QuestionnaireFactory,
    QuestionnaireTypeFactory,
)


def by_token_url(token):
    return f"/api/questionnaires/by-token/{token}/"


def submit_url(token):
    return f"/api/questionnaires/by-token/{token}/submit/"


def battery_by_token_url(token):
    return f"/api/batteries/by-token/{token}/"


@pytest.fixture
def questionnaire(qtype):
    return QuestionnaireFactory(questionnaire_type=qtype, name="Alice")


def test_anonymous_can_fetch_by_token(api_client, questionnaire, qtype):
    response = api_client.get(by_token_url(questionnaire.share_token))
    assert response.status_code == 200
    assert response.data["id"] == str(questionnaire.id)
    assert response.data["questionnaireTypeTitle"] == qtype.title
    assert response.data["questionnaireJson"] == qtype.questionnaire_json
    assert response.data["submittedAt"] is None


def test_public_payload_has_no_owner(api_client, questionnaire):
    data = api_client.get(by_token_url(questionnaire.share_token)).data
    assert set(data) == {
        "id",
        "name",
        "questionnaireTypeTitle",
        "questionnaireJson",
        "submittedAt",
    }


def test_stale_jwt_does_not_401(api_client, questionnaire):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
    response = api_client.get(by_token_url(questionnaire.share_token))
    assert response.status_code == 200


def test_anonymous_can_submit(api_client, questionnaire):
    payload = {"answers": {"q1": "hello"}, "metrics": {"totalScore": 7}}
    response = api_client.patch(
        submit_url(questionnaire.share_token), payload, format="json"
    )
    assert response.status_code == 200
    assert response.data["submittedAt"] is not None
    questionnaire.refresh_from_db()
    assert questionnaire.answers_json == {"q1": "hello"}
    assert questionnaire.metrics_json == {"totalScore": 7}


def test_submit_without_metrics_defaults_to_empty(api_client, questionnaire):
    response = api_client.patch(
        submit_url(questionnaire.share_token), {"answers": {}}, format="json"
    )
    assert response.status_code == 200
    questionnaire.refresh_from_db()
    assert questionnaire.metrics_json == {}


def test_submit_rejects_non_object_answers(api_client, questionnaire):
    response = api_client.patch(
        submit_url(questionnaire.share_token), {"answers": [1, 2]}, format="json"
    )
    assert response.status_code == 400


def test_second_submit_returns_409(api_client, questionnaire):
    url = submit_url(questionnaire.share_token)
    assert (
        api_client.patch(url, {"answers": {"q1": "a"}}, format="json").status_code
        == 200
    )
    response = api_client.patch(url, {"answers": {"q1": "b"}}, format="json")
    assert response.status_code == 409
    questionnaire.refresh_from_db()
    assert questionnaire.answers_json == {"q1": "a"}


def test_submit_snapshots_type_json(api_client, questionnaire, qtype):
    original = qtype.questionnaire_json
    api_client.patch(
        submit_url(questionnaire.share_token), {"answers": {}}, format="json"
    )
    qtype.questionnaire_json = {"pages": [{"name": "changed", "elements": []}]}
    qtype.save()
    questionnaire.refresh_from_db()
    assert questionnaire.questionnaire_json_snapshot == original
    # The taker sees the definition it was answered against, not the edited one.
    data = api_client.get(by_token_url(questionnaire.share_token)).data
    assert data["questionnaireJson"] == original


@pytest.mark.parametrize("token", [uuid.uuid4(), "not-a-uuid"])
@pytest.mark.django_db
def test_invalid_token_404(api_client, token):
    assert api_client.get(by_token_url(token)).status_code == 404
    assert (
        api_client.patch(submit_url(token), {"answers": {}}, format="json").status_code
        == 404
    )
    assert api_client.get(battery_by_token_url(token)).status_code == 404


def test_owner_endpoints_stay_private(api_client, questionnaire):
    assert api_client.get(f"/api/questionnaires/{questionnaire.id}/").status_code == 401


def test_battery_by_token_lists_slots_in_order(api_client, user):
    qt_a = QuestionnaireTypeFactory(owner=user, title="A")
    qt_b = QuestionnaireTypeFactory(owner=user, title="B")
    battery = services.create_battery(
        BatteryTypeFactory(
            owner=user, title="Intake", questionnaire_types=[qt_b, qt_a]
        ),
        "Bob",
    )
    response = api_client.get(battery_by_token_url(battery.share_token))
    assert response.status_code == 200
    data = response.data
    assert set(data) == {
        "id",
        "name",
        "batteryTypeName",
        "questionnaires",
        "isComplete",
    }
    assert data["batteryTypeName"] == "Intake"
    assert data["isComplete"] is False
    slots = data["questionnaires"]
    assert [s["order"] for s in slots] == [0, 1]
    assert [s["questionnaireTypeName"] for s in slots] == ["B", "A"]
    assert set(slots[0]) == {
        "order",
        "shareToken",
        "questionnaireTypeName",
        "submittedAt",
    }


def test_battery_completes_after_all_slots_submitted(api_client, user, qtype):
    battery = services.create_battery(
        BatteryTypeFactory(owner=user, questionnaire_types=[qtype, qtype])
    )
    url = battery_by_token_url(battery.share_token)
    for slot in api_client.get(url).data["questionnaires"]:
        api_client.patch(submit_url(slot["shareToken"]), {"answers": {}}, format="json")
    assert api_client.get(url).data["isComplete"] is True
