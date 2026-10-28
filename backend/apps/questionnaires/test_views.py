import uuid

import pytest

from . import services
from .factories import (
    BatteryTypeFactory,
    QuestionnaireFactory,
    QuestionnaireTypeFactory,
)
from .models import Battery, BatteryType, Questionnaire, QuestionnaireType

TYPES_URL = "/api/questionnaire-types/"
QUESTIONNAIRES_URL = "/api/questionnaires/"
BATTERY_TYPES_URL = "/api/battery-types/"
BATTERIES_URL = "/api/batteries/"


def detail(base, pk):
    return f"{base}{pk}/"


# ── Auth and ownership ────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url", [TYPES_URL, QUESTIONNAIRES_URL, BATTERY_TYPES_URL, BATTERIES_URL]
)
def test_list_requires_auth(api_client, url):
    assert api_client.get(url).status_code == 401


@pytest.mark.django_db
def test_detail_requires_auth(api_client, qtype):
    assert api_client.get(detail(TYPES_URL, qtype.id)).status_code == 401


def test_user_only_sees_own_types(auth_client, other_client, qtype, other_user):
    QuestionnaireTypeFactory(owner=other_user)
    own = auth_client.get(TYPES_URL).data
    assert [t["id"] for t in own] == [str(qtype.id)]
    assert str(qtype.id) not in [t["id"] for t in other_client.get(TYPES_URL).data]
    assert other_client.get(detail(TYPES_URL, qtype.id)).status_code == 404
    assert (
        other_client.patch(detail(TYPES_URL, qtype.id), {"title": "x"}).status_code
        == 404
    )
    assert other_client.delete(detail(TYPES_URL, qtype.id)).status_code == 404


def test_user_only_sees_own_instances(auth_client, other_client, qtype):
    q = QuestionnaireFactory(questionnaire_type=qtype)
    battery = services.create_battery(
        BatteryTypeFactory(owner=qtype.owner, questionnaire_types=[qtype])
    )
    assert other_client.get(QUESTIONNAIRES_URL).data == []
    assert other_client.get(BATTERIES_URL).data == []
    assert other_client.get(detail(QUESTIONNAIRES_URL, q.id)).status_code == 404
    assert other_client.get(detail(BATTERIES_URL, battery.id)).status_code == 404
    assert len(auth_client.get(QUESTIONNAIRES_URL).data) == 2


def test_create_sets_owner(auth_client, user):
    response = auth_client.post(
        TYPES_URL, {"title": "New", "questionnaireJson": {"pages": []}}, format="json"
    )
    assert response.status_code == 201
    assert QuestionnaireType.objects.get(id=response.data["id"]).owner == user
    assert "owner" not in response.data


def test_create_ignores_owner_in_payload(auth_client, user, other_user):
    response = auth_client.post(
        TYPES_URL, {"title": "New", "owner": str(other_user.id)}, format="json"
    )
    assert QuestionnaireType.objects.get(id=response.data["id"]).owner == user


# ── Questionnaire types ───────────────────────────────────────────────────────


def test_type_create_requires_title(auth_client):
    response = auth_client.post(TYPES_URL, {}, format="json")
    assert response.status_code == 400
    assert "title" in response.data


def test_type_returns_camel_case_fields(auth_client, qtype):
    data = auth_client.get(detail(TYPES_URL, qtype.id)).data
    assert set(data) == {"id", "title", "questionnaireJson", "createdAt", "updatedAt"}


def test_type_patch_questionnaire_json(auth_client, qtype):
    new_json = {"pages": [{"name": "recipient_page", "elements": []}]}
    response = auth_client.patch(
        detail(TYPES_URL, qtype.id), {"questionnaireJson": new_json}, format="json"
    )
    assert response.status_code == 200
    qtype.refresh_from_db()
    assert qtype.questionnaire_json == new_json


def test_type_put_not_allowed(auth_client, qtype):
    assert (
        auth_client.put(detail(TYPES_URL, qtype.id), {"title": "x"}).status_code == 405
    )


def test_delete_unused_type(auth_client, qtype):
    assert auth_client.delete(detail(TYPES_URL, qtype.id)).status_code == 204
    assert not QuestionnaireType.objects.exists()


def test_delete_type_with_instances_is_blocked(auth_client, qtype):
    QuestionnaireFactory(questionnaire_type=qtype)
    response = auth_client.delete(detail(TYPES_URL, qtype.id))
    assert response.status_code == 409
    assert QuestionnaireType.objects.filter(id=qtype.id).exists()


def test_delete_type_in_battery_type_is_blocked(auth_client, user, qtype):
    BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
    assert auth_client.delete(detail(TYPES_URL, qtype.id)).status_code == 409


# ── Questionnaire instances ───────────────────────────────────────────────────


def test_create_questionnaire(auth_client, user, qtype):
    response = auth_client.post(
        QUESTIONNAIRES_URL,
        {"questionnaireTypeId": str(qtype.id), "name": "Alice"},
        format="json",
    )
    assert response.status_code == 201
    q = Questionnaire.objects.get(id=response.data["id"])
    assert q.owner == user
    assert response.data["shareToken"] == str(q.share_token)
    assert response.data["submittedAt"] is None
    assert response.data["questionnaireType"]["id"] == str(qtype.id)
    assert "questionnaireJsonSnapshot" in response.data
    assert "surveyJsonSnapshot" not in response.data


def test_create_questionnaire_rejects_foreign_type(auth_client, other_user):
    foreign = QuestionnaireTypeFactory(owner=other_user)
    response = auth_client.post(
        QUESTIONNAIRES_URL, {"questionnaireTypeId": str(foreign.id)}, format="json"
    )
    assert response.status_code == 400
    assert "questionnaireTypeId" in response.data


def test_owner_cannot_write_answers(auth_client, qtype):
    q = QuestionnaireFactory(questionnaire_type=qtype)
    response = auth_client.patch(
        detail(QUESTIONNAIRES_URL, q.id),
        {"name": "Bob", "answers": {"q1": "x"}},
        format="json",
    )
    assert response.status_code == 200
    q.refresh_from_db()
    assert q.name == "Bob"
    assert q.answers_json == {}


def test_questionnaire_type_cannot_change(auth_client, user, qtype):
    q = QuestionnaireFactory(questionnaire_type=qtype)
    other_type = QuestionnaireTypeFactory(owner=user)
    response = auth_client.patch(
        detail(QUESTIONNAIRES_URL, q.id),
        {"questionnaireTypeId": str(other_type.id)},
        format="json",
    )
    assert response.status_code == 400


def test_delete_questionnaire(auth_client, qtype):
    q = QuestionnaireFactory(questionnaire_type=qtype)
    assert auth_client.delete(detail(QUESTIONNAIRES_URL, q.id)).status_code == 204
    assert not Questionnaire.objects.exists()


# ── Battery types ─────────────────────────────────────────────────────────────


def test_battery_type_create_keeps_order(auth_client, user):
    qt1, qt2 = (
        QuestionnaireTypeFactory(owner=user),
        QuestionnaireTypeFactory(owner=user),
    )
    ids = [str(qt2.id), str(qt1.id)]
    response = auth_client.post(
        BATTERY_TYPES_URL, {"title": "BT", "questionnaireTypeIds": ids}, format="json"
    )
    assert response.status_code == 201
    assert response.data["questionnaireTypeIds"] == ids
    bt = BatteryType.objects.get(id=response.data["id"])
    assert bt.owner == user
    assert list(bt.items.values_list("questionnaire_type_id", flat=True)) == [
        qt2.id,
        qt1.id,
    ]


def test_battery_type_rejects_foreign_type_ids(auth_client, user, other_user):
    own = QuestionnaireTypeFactory(owner=user)
    foreign = QuestionnaireTypeFactory(owner=other_user)
    response = auth_client.post(
        BATTERY_TYPES_URL,
        {"title": "BT", "questionnaireTypeIds": [str(own.id), str(foreign.id)]},
        format="json",
    )
    assert response.status_code == 400
    assert "questionnaireTypeIds" in response.data
    assert not BatteryType.objects.exists()


def test_battery_type_patch_replaces_items(auth_client, user):
    qt1, qt2 = (
        QuestionnaireTypeFactory(owner=user),
        QuestionnaireTypeFactory(owner=user),
    )
    bt = BatteryTypeFactory(owner=user, questionnaire_types=[qt1])
    response = auth_client.patch(
        detail(BATTERY_TYPES_URL, bt.id),
        {"questionnaireTypeIds": [str(qt2.id), str(qt1.id)]},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["questionnaireTypeIds"] == [str(qt2.id), str(qt1.id)]


def test_battery_type_patch_title_keeps_items(auth_client, user, qtype):
    bt = BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
    response = auth_client.patch(
        detail(BATTERY_TYPES_URL, bt.id), {"title": "Renamed"}, format="json"
    )
    assert response.data["title"] == "Renamed"
    assert response.data["questionnaireTypeIds"] == [str(qtype.id)]


def test_battery_type_list_shape(auth_client, user, qtype):
    BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
    (data,) = auth_client.get(BATTERY_TYPES_URL).data
    assert set(data) == {
        "id",
        "title",
        "description",
        "questionnaireTypeIds",
        "createdAt",
        "updatedAt",
    }


def test_delete_battery_type_with_batteries_is_blocked(auth_client, user):
    bt = BatteryTypeFactory(owner=user)
    services.create_battery(bt)
    assert auth_client.delete(detail(BATTERY_TYPES_URL, bt.id)).status_code == 409


# ── Batteries ─────────────────────────────────────────────────────────────────


def test_create_battery_creates_ordered_questionnaires(auth_client, user):
    qt1, qt2 = (
        QuestionnaireTypeFactory(owner=user, title="A"),
        QuestionnaireTypeFactory(owner=user, title="B"),
    )
    bt = BatteryTypeFactory(owner=user, questionnaire_types=[qt2, qt1])
    response = auth_client.post(
        BATTERIES_URL, {"batteryTypeId": str(bt.id), "name": "Run 1"}, format="json"
    )
    assert response.status_code == 201
    assert response.data["name"] == "Run 1"
    assert response.data["batteryTypeName"] == bt.title
    assert response.data["isComplete"] is False
    slots = response.data["questionnaires"]
    assert [s["order"] for s in slots] == [0, 1]
    assert [s["questionnaireTypeName"] for s in slots] == ["B", "A"]
    assert Battery.objects.get(id=response.data["id"]).owner == user


def test_create_battery_rejects_foreign_battery_type(auth_client, other_user):
    bt = BatteryTypeFactory(owner=other_user)
    response = auth_client.post(
        BATTERIES_URL, {"batteryTypeId": str(bt.id)}, format="json"
    )
    assert response.status_code == 400


def test_battery_is_complete_when_all_submitted(auth_client, user, qtype):
    battery = services.create_battery(
        BatteryTypeFactory(owner=user, questionnaire_types=[qtype, qtype])
    )
    for q in battery.questionnaires.all():
        services.submit_questionnaire(q, {}, {})
    assert auth_client.get(detail(BATTERIES_URL, battery.id)).data["isComplete"] is True


def test_battery_list_query_count(
    auth_client, user, qtype, django_assert_max_num_queries
):
    bt = BatteryTypeFactory(owner=user, questionnaire_types=[qtype, qtype])
    for _ in range(3):
        services.create_battery(bt)
    with django_assert_max_num_queries(3):
        assert len(auth_client.get(BATTERIES_URL).data) == 3


def test_battery_patch_not_allowed(auth_client, user):
    battery = services.create_battery(BatteryTypeFactory(owner=user))
    assert (
        auth_client.patch(detail(BATTERIES_URL, battery.id), {"name": "x"}).status_code
        == 405
    )


def test_delete_battery(auth_client, user):
    battery = services.create_battery(BatteryTypeFactory(owner=user))
    assert auth_client.delete(detail(BATTERIES_URL, battery.id)).status_code == 204


def test_unknown_id_is_404(auth_client):
    assert auth_client.get(detail(TYPES_URL, uuid.uuid4())).status_code == 404
