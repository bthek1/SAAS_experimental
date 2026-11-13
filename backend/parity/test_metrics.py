"""`/metrics` answers only Prometheus: a direct peer inside the allowed CIDRs (#9).

The server listens on 127.0.0.1 and allows 127.0.0.1/32 by default, so a request
sent from 127.0.0.2 (also loopback on Linux) is a peer outside the list.
"""

import httpx
import pytest


def test_scrape_from_an_allowed_peer(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "app_outbox_pending_events" in response.text
    assert "app_outbox_oldest_pending_seconds" in response.text


@pytest.mark.parametrize("header", ["X-Forwarded-For", "X-Real-IP", "Forwarded"])
def test_a_forwarded_request_is_not_found(client, header):
    assert client.get("/metrics", headers={header: "203.0.113.9"}).status_code == 404


def test_a_peer_outside_the_list_is_not_found(base_url):
    transport = httpx.HTTPTransport(local_address="127.0.0.2")
    with httpx.Client(base_url=base_url, transport=transport) as outsider:
        assert outsider.get("/metrics").status_code == 404
        # The address works for the rest of the API.
        assert outsider.get("/api/health/").status_code == 200


def test_only_get(client):
    assert client.post("/metrics").status_code == 404


def test_undelivered_events_show_on_the_gauge(client, owner, stub):  # noqa: ARG001
    stub.events_status = 500
    client.post("/api/questionnaire-types/", json={"title": "stuck"})
    lines = [
        line
        for line in client.get("/metrics").text.splitlines()
        if line.startswith("app_outbox_pending_events")
    ]
    assert lines
    assert float(lines[0].split()[-1]) >= 1
