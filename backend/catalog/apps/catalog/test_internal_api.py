"""`/internal/` on `catalog`, and the HTTP client that calls `instances` (#13)."""

import uuid

import httpx
import pytest
from common.peers import PeerUnavailable, RefInUse
from django.conf import settings

from . import internal_views
from .factories import QuestionnaireTypeFactory
from .instances_client import HttpInstances

pytestmark = pytest.mark.django_db


def test_missing_token_is_refused(api_client, qtype):
    response = api_client.get(f"/internal/questionnaire-types/{qtype.pk}/")
    assert response.status_code == 403


def test_wrong_direction_token_is_refused(api_client, qtype):
    # catalog's own outbound token is what it sends, never what it accepts.
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {settings.CATALOG_TO_INSTANCES_TOKEN}"
    )
    response = api_client.get(f"/internal/questionnaire-types/{qtype.pk}/")
    assert response.status_code == 403


def test_a_user_token_is_not_an_internal_token(api_client, qtype):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer not-the-token")
    response = api_client.get(f"/internal/questionnaire-types/{qtype.pk}/")
    assert response.status_code == 403


def test_unset_token_refuses_everyone(api_client, qtype, settings):
    settings.PEER_INBOUND_TOKEN = ""
    api_client.credentials(HTTP_AUTHORIZATION="Bearer ")
    response = api_client.get(f"/internal/questionnaire-types/{qtype.pk}/")
    assert response.status_code == 403


def test_fetch(internal_client, qtype):
    response = internal_client.get(f"/internal/questionnaire-types/{qtype.pk}/")
    assert response.status_code == 200
    assert response.json()["aggregateId"] == str(qtype.pk)


def test_unknown_type_is_404(internal_client):
    response = internal_client.get(f"/internal/questionnaire-types/{uuid.uuid4()}/")
    assert response.status_code == 404


def test_list_walks_every_type_by_id(internal_client, user, monkeypatch):
    monkeypatch.setattr(internal_views, "PAGE_SIZE", 2)
    created = [QuestionnaireTypeFactory(owner=user) for _ in range(5)]
    seen, after = [], None
    while True:
        params = {"after": after} if after else {}
        page = internal_client.get("/internal/questionnaire-types/", params).json()
        seen += [row["aggregateId"] for row in page["results"]]
        after = page["next"]
        if after is None:
            break
    assert sorted(seen) == sorted(str(qt.pk) for qt in created)


def test_health_needs_no_token(api_client):
    assert api_client.get("/internal/health/").status_code == 200


class TestHttpInstances:
    def answer(self, mocker, status):
        return mocker.patch(
            "common.peers.httpx.request",
            return_value=httpx.Response(status, json={}),
        )

    def test_sends_the_event_with_the_outbound_token(self, mocker):
        request = self.answer(mocker, 200)
        HttpInstances().send_event({"type": "x"})
        args, kwargs = request.call_args
        assert args == ("POST", f"{settings.INSTANCES_INTERNAL_URL}/internal/events/")
        assert kwargs["json"] == {"type": "x"}
        assert kwargs["headers"]["Authorization"] == (
            f"Bearer {settings.CATALOG_TO_INSTANCES_TOKEN}"
        )

    def test_refused_event_is_not_peer_unavailable(self, mocker):
        self.answer(mocker, 400)
        with pytest.raises(ValueError, match="refused"):
            HttpInstances().send_event({})

    @pytest.mark.parametrize("status", [401, 403, 500, 503])
    def test_a_bad_answer_is_peer_unavailable(self, mocker, status):
        self.answer(mocker, status)
        with pytest.raises(PeerUnavailable):
            HttpInstances().send_event({})

    def test_no_answer_is_peer_unavailable(self, mocker):
        mocker.patch(
            "common.peers.httpx.request", side_effect=httpx.ConnectError("refused")
        )
        with pytest.raises(PeerUnavailable):
            HttpInstances().retire("questionnaire_type", uuid.uuid4())

    def test_retire_in_use(self, mocker):
        self.answer(mocker, 409)
        with pytest.raises(RefInUse):
            HttpInstances().retire("questionnaire_type", uuid.uuid4())

    def test_retire_ok(self, mocker):
        self.answer(mocker, 204)
        HttpInstances().retire("questionnaire_type", uuid.uuid4())

    @pytest.mark.parametrize("status", [200, 404])
    def test_retire_fails_closed_on_anything_else(self, mocker, status):
        self.answer(mocker, status)
        with pytest.raises(PeerUnavailable):
            HttpInstances().retire("questionnaire_type", uuid.uuid4())
