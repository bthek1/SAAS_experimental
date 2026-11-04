"""/metrics (#9): served to the Prometheus scraper only, never through a proxy."""

import pytest
from django.test import Client, override_settings

URL = "/metrics"


@pytest.fixture
def client():
    return Client()


def test_served_to_an_allowed_peer(client):
    response = client.get(URL)  # the test client's REMOTE_ADDR is 127.0.0.1
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    assert b"django_http_requests_before_middlewares_total" in response.content


def test_trailing_slash_is_the_same_endpoint(client):
    assert client.get(f"{URL}/").status_code == 200


@override_settings(METRICS_ALLOWED_CIDRS=["192.168.2.243/32"])
def test_served_to_the_monitor_by_ip_over_plain_http(client):
    # Prometheus scrapes by IP (not in ALLOWED_HOSTS) and over HTTP, which
    # prod redirects. Neither may get in the way.
    with override_settings(SECURE_SSL_REDIRECT=True):
        response = client.get(
            URL, REMOTE_ADDR="192.168.2.243", HTTP_HOST="192.168.2.241:8000"
        )
    assert response.status_code == 200


@override_settings(METRICS_ALLOWED_CIDRS=["192.168.2.243/32"])
@pytest.mark.parametrize("peer", ["127.0.0.1", "192.168.2.244", "8.8.8.8", ""])
def test_hidden_from_other_peers(client, peer):
    assert client.get(URL, REMOTE_ADDR=peer).status_code == 404


@pytest.mark.parametrize(
    "header",
    ["HTTP_X_FORWARDED_FOR", "HTTP_X_REAL_IP", "HTTP_FORWARDED"],
)
def test_hidden_behind_a_proxy(client, header):
    assert client.get(URL, **{header: "127.0.0.1"}).status_code == 404


def test_only_get(client):
    assert client.post(URL).status_code == 404


@pytest.mark.django_db
def test_not_under_api(client):
    assert client.get("/api/metrics/").status_code == 404


@pytest.mark.django_db
def test_other_paths_pass_through(client):
    assert client.get("/api/health/").status_code == 200
