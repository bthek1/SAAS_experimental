"""`/metrics` answers only Prometheus, and `/internal/health/` answers anyone (#9, #13).

The server listens on 127.0.0.1 and allows 127.0.0.1/32 by default, so a request
sent from 127.0.0.2 (also loopback on Linux) is a peer outside the list.
"""

import httpx
import pytest


def test_scrape_from_an_allowed_peer(anon):
    response = anon.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# TYPE" in response.text


@pytest.mark.parametrize("header", ["X-Forwarded-For", "X-Real-IP", "Forwarded"])
def test_a_forwarded_request_is_not_found(anon, header):
    assert anon.get("/metrics", headers={header: "203.0.113.9"}).status_code == 404


def test_a_peer_outside_the_list_is_not_found(base_url):
    transport = httpx.HTTPTransport(local_address="127.0.0.2")
    with httpx.Client(base_url=base_url, transport=transport) as outsider:
        assert outsider.get("/metrics").status_code == 404
        # The address works for everything else.
        assert outsider.get("/internal/health/").status_code == 200


def test_only_get(anon):
    assert anon.post("/metrics").status_code == 404


def test_health_needs_no_token(anon):
    response = anon.get("/internal/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
