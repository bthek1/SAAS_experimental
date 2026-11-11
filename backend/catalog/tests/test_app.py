"""Middleware and error shapes the parity suite can't reach (#35, #37).

Parity runs one profile over loopback. These build the app with other settings: a
prod-like HTTPS redirect, a host outside ALLOWED_HOSTS, a CORS preflight.
"""

import pytest
from fastapi.testclient import TestClient

from catalog.app import create_app
from catalog.settings import get_settings

ORIGIN = "http://localhost:5174"


def app_with(**changes) -> TestClient:
    settings = get_settings().model_copy(update=changes)
    return TestClient(create_app(settings), base_url="http://testserver")


def test_unknown_host_is_refused():
    with app_with() as client:
        response = client.get("/api/health/", headers={"Host": "evil.example.com"})
    assert response.status_code == 400


def test_django_style_subdomain_hosts():
    with app_with(allowed_hosts=[".example.com"]) as client:
        ok = client.get("/api/health/", headers={"Host": "api.example.com"})
        refused = client.get("/api/health/", headers={"Host": "example.org"})
    assert ok.status_code == 200
    assert refused.status_code == 400


@pytest.fixture
def https_app():
    with app_with(https_redirect=True, hsts_seconds=60) as client:
        yield client


def test_plain_http_is_redirected(https_app):
    response = https_app.get("/api/health/?a=1", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "https://testserver/api/health/?a=1"


def test_internal_is_never_redirected(https_app):
    # The services call each other over plain HTTP on a private network.
    response = https_app.get("/internal/health/", follow_redirects=False)
    assert response.status_code == 200


def test_https_responses_carry_hsts(https_app):
    response = https_app.get("https://testserver/api/health/")
    assert response.status_code == 200
    assert response.headers["strict-transport-security"].startswith("max-age=60")


def test_cors_preflight_from_the_spa(client):
    response = client.options(
        "/api/token/",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_cors_refuses_another_origin(client):
    response = client.get("/api/health/", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_exposes_content_disposition(client):
    response = client.get("/api/health/", headers={"Origin": ORIGIN})
    exposed = response.headers["access-control-expose-headers"].lower()
    assert "content-disposition" in exposed


def test_openapi_only_under_debug(client):
    assert client.get("/api/docs/").status_code == 404
    with app_with(debug=True) as debug_client:
        assert debug_client.get("/api/docs/").status_code == 200


# ── Error shapes the SPA reads ─────────────────────────────────────────────────


def test_a_body_that_is_not_an_object(client):
    response = client.post("/api/accounts/register/", json=["not", "a", "dict"])
    assert response.status_code == 400
    assert response.json() == {
        "non_field_errors": ["Invalid data. Expected a dictionary, but got list."]
    }


def test_malformed_json(client):
    response = client.post(
        "/api/accounts/register/",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("JSON parse error")


def test_unknown_path(client):
    response = client.get("/api/nothing-here/")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found."}


def test_wrong_method_names_it(client):
    response = client.put("/api/health/")
    assert response.status_code == 405
    assert response.json() == {"detail": 'Method "PUT" not allowed.'}


def test_null_is_not_blank(auth):
    response = auth.post("/api/questionnaire-types/", json={"title": None})
    assert response.json() == {"title": ["This field may not be null."]}
    response = auth.post("/api/questionnaire-types/", json={"title": "   "})
    assert response.json() == {"title": ["This field may not be blank."]}


def test_a_client_that_leaves_mid_body_is_not_an_error(caplog):
    # k6 aborting a stress run left 117 tracebacks in catalog's journal (#38).
    import asyncio

    from starlette.types import Message

    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/token/",
        "raw_path": b"/api/token/",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }
    asyncio.run(create_app()(scope, receive, send))
    assert sent[0]["status"] == 499
    assert "Traceback" not in caplog.text
