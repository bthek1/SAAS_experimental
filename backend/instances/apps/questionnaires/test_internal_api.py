"""`/internal/` on `instances`, its client for `catalog`, and the hot path (#13)."""

import uuid

import httpx
import pytest
from common.peers import PeerUnavailable
from django.conf import settings

from .catalog_client import HttpCatalog
from .factories import (
    BatteryTypeFactory,
    QuestionnaireFactory,
    QuestionnaireTypeFactory,
)
from .models import QuestionnaireTypeRef, RetiredRef

pytestmark = pytest.mark.django_db


def retire_url(ref_id, kind="questionnaire_type"):
    return f"/internal/refs/{kind}/{ref_id}/retire/"


def test_missing_token_is_refused(api_client):
    assert api_client.post("/internal/events/", {}, format="json").status_code == 403


def test_wrong_direction_token_is_refused(api_client, qtype):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {settings.INSTANCES_TO_CATALOG_TOKEN}"
    )
    assert api_client.post(retire_url(qtype.pk)).status_code == 403
    assert QuestionnaireTypeRef.objects.filter(pk=qtype.pk).exists()


def test_unset_token_refuses_everyone(api_client, settings):
    settings.PEER_INBOUND_TOKEN = ""
    api_client.credentials(HTTP_AUTHORIZATION="Bearer ")
    assert api_client.post("/internal/events/", {}, format="json").status_code == 403


def test_malformed_event_is_400_so_it_is_not_retried_forever(internal_client):
    response = internal_client.post(
        "/internal/events/", {"type": "nonsense.thing"}, format="json"
    )
    assert response.status_code == 400


def test_retire(internal_client, qtype):
    assert internal_client.post(retire_url(qtype.pk)).status_code == 204
    assert not QuestionnaireTypeRef.objects.filter(pk=qtype.pk).exists()
    assert RetiredRef.objects.filter(ref_id=qtype.pk).exists()


def test_retire_in_use_is_409(internal_client, qtype):
    QuestionnaireFactory(questionnaire_type=qtype)
    assert internal_client.post(retire_url(qtype.pk)).status_code == 409


def test_retire_unknown_kind_is_404(internal_client):
    response = internal_client.post(retire_url(uuid.uuid4(), kind="nonsense"))
    assert response.status_code == 404


def test_health_needs_no_token(api_client):
    assert api_client.get("/internal/health/").status_code == 200


class TestHttpCatalog:
    def test_404_means_no_such_type(self, mocker):
        mocker.patch(
            "common.peers.httpx.request", return_value=httpx.Response(404, json={})
        )
        assert HttpCatalog().fetch("questionnaire_type", uuid.uuid4()) is None

    def test_no_answer_is_peer_unavailable(self, mocker):
        mocker.patch(
            "common.peers.httpx.request", side_effect=httpx.ConnectError("refused")
        )
        with pytest.raises(PeerUnavailable):
            HttpCatalog().fetch("questionnaire_type", uuid.uuid4())

    def test_sends_the_outbound_token(self, mocker):
        request = mocker.patch(
            "common.peers.httpx.request", return_value=httpx.Response(404, json={})
        )
        HttpCatalog().fetch("battery_type", uuid.uuid4())
        assert request.call_args.kwargs["headers"]["Authorization"] == (
            f"Bearer {settings.INSTANCES_TO_CATALOG_TOKEN}"
        )


def test_no_network_on_hot_path(auth_client, api_client, user, settings, mocker):
    """The whole point of the copies: `catalog` can be down for all of this."""
    settings.CATALOG_CLIENT = "apps.questionnaires.catalog_client.HttpCatalog"
    blocked = mocker.patch(
        "common.peers.httpx.request", side_effect=AssertionError("network call")
    )
    qtype = QuestionnaireTypeFactory(owner=user)
    battery_type = BatteryTypeFactory(owner=user, questionnaire_types=[qtype])

    created = auth_client.post(
        "/api/questionnaires/", {"questionnaireTypeId": str(qtype.pk)}, format="json"
    )
    assert created.status_code == 201
    battery = auth_client.post(
        "/api/batteries/", {"batteryTypeId": str(battery_type.pk)}, format="json"
    )
    assert battery.status_code == 201

    url = f"/api/questionnaires/by-token/{created.data['shareToken']}/"
    assert api_client.get(url).status_code == 200
    submitted = api_client.patch(
        f"{url}submit/", {"answers": {"q1": "a"}, "metrics": {"t": 1}}, format="json"
    )
    assert submitted.status_code == 200

    assert auth_client.get("/api/dashboard/").status_code == 200
    scores = auth_client.get("/api/dashboard/scores/", {"questionnaireType": qtype.pk})
    assert scores.status_code == 200
    blocked.assert_not_called()
