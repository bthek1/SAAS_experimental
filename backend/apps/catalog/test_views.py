import pytest

from .factories import BatteryTypeFactory, QuestionnaireTypeFactory
from .models import BatteryType, QuestionnaireType

TYPES_URL = "/api/questionnaire-types/"
BATTERY_TYPES_URL = "/api/battery-types/"


def detail(base, pk):
    return f"{base}{pk}/"


@pytest.mark.django_db
def test_detail_requires_auth(api_client, qtype):
    assert api_client.get(detail(TYPES_URL, qtype.id)).status_code == 401


def test_user_only_sees_own_types(auth_client, other_client, qtype, other_user):
    QuestionnaireTypeFactory(owner=other_user)
    own = auth_client.get(TYPES_URL).data["results"]
    assert [t["id"] for t in own] == [str(qtype.id)]
    assert str(qtype.id) not in [
        t["id"] for t in other_client.get(TYPES_URL).data["results"]
    ]
    assert other_client.get(detail(TYPES_URL, qtype.id)).status_code == 404
    assert (
        other_client.patch(detail(TYPES_URL, qtype.id), {"title": "x"}).status_code
        == 404
    )
    assert other_client.delete(detail(TYPES_URL, qtype.id)).status_code == 404


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


def test_delete_type_in_battery_type_is_blocked(auth_client, user, qtype):
    BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
    assert auth_client.delete(detail(TYPES_URL, qtype.id)).status_code == 409


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
    (data,) = auth_client.get(BATTERY_TYPES_URL).data["results"]
    assert set(data) == {
        "id",
        "title",
        "description",
        "questionnaireTypeIds",
        "createdAt",
        "updatedAt",
    }
