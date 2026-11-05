"""The HTTP client for `catalog`: anything but a clean answer means it's unavailable."""

import pytest
from common.peers import PeerUnavailable

from .catalog_client import HttpCatalog


@pytest.fixture
def peer(mocker):
    return mocker.patch("apps.questionnaires.catalog_client.peer_request")


def answer(status: int, body=None):
    class Response:
        status_code = status

        def json(self):
            return body

    return Response()


def test_fetch_returns_the_snapshot(peer):
    peer.return_value = answer(200, {"aggregateId": "a"})
    assert HttpCatalog().fetch("questionnaire_type", "a") == {"aggregateId": "a"}
    assert peer.call_args.args[2] == "/internal/questionnaire-types/a/"


def test_fetch_of_an_unknown_type_is_none(peer):
    """A real "no", which callers must be able to tell from "can't say"."""
    peer.return_value = answer(404)
    assert HttpCatalog().fetch("battery_type", "a") is None


@pytest.mark.parametrize("status", [401, 500, 502, 503])
def test_fetch_treats_other_statuses_as_unavailable(peer, status):
    peer.return_value = answer(status)
    with pytest.raises(PeerUnavailable, match=str(status)):
        HttpCatalog().fetch("questionnaire_type", "a")


def test_iter_snapshots_follows_the_cursor(peer):
    peer.side_effect = [
        answer(200, {"results": [{"n": 1}], "next": "cursor"}),
        answer(200, {"results": [{"n": 2}], "next": None}),
    ]

    assert list(HttpCatalog().iter_snapshots("battery_type")) == [{"n": 1}, {"n": 2}]
    assert peer.call_args_list[0].kwargs["params"] == {}
    assert peer.call_args_list[1].kwargs["params"] == {"after": "cursor"}


def test_iter_snapshots_stops_on_a_failed_page(peer):
    """A partial list must not look complete, or a reconcile would act on it."""
    peer.side_effect = [
        answer(200, {"results": [{"n": 1}], "next": "cursor"}),
        answer(500),
    ]
    with pytest.raises(PeerUnavailable, match="500"):
        list(HttpCatalog().iter_snapshots("questionnaire_type"))
