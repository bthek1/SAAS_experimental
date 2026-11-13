from .conftest import PASSWORD, register, unique_email


def test_register_returns_id_and_email(client):
    email = unique_email()
    response = client.post(
        "/api/accounts/register/", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email"}
    assert body["email"] == email


def test_register_duplicate_email_is_a_field_error(client):
    email = register(client)["email"]
    response = client.post(
        "/api/accounts/register/", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 400
    body = response.json()
    assert list(body) == ["email"]
    assert isinstance(body["email"], list)
    assert isinstance(body["email"][0], str)


def test_register_short_password_is_a_field_error(client):
    response = client.post(
        "/api/accounts/register/", json={"email": unique_email(), "password": "short"}
    )
    assert response.status_code == 400
    assert list(response.json()) == ["password"]


def test_register_missing_fields(client):
    response = client.post("/api/accounts/register/", json={})
    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"email", "password"}
    assert all(isinstance(messages, list) for messages in body.values())


def test_register_invalid_email(client):
    response = client.post(
        "/api/accounts/register/", json={"email": "not-an-email", "password": PASSWORD}
    )
    assert response.status_code == 400
    assert list(response.json()) == ["email"]


def test_me_returns_the_user(client, owner):
    response = client.get("/api/accounts/me/")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "email", "first_name", "last_name", "date_joined"}
    assert body["id"] == owner["id"]
    assert body["email"] == owner["email"]
    assert body["first_name"] == ""
    assert body["last_name"] == ""


def test_me_patch_changes_names_only(client, owner):
    response = client.patch(
        "/api/accounts/me/",
        json={"first_name": "Ada", "last_name": "Lovelace", "id": "ignored"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["first_name"], body["last_name"]) == ("Ada", "Lovelace")
    assert body["id"] == owner["id"]
    assert client.get("/api/accounts/me/").json()["first_name"] == "Ada"


def test_me_needs_a_token(client):
    response = client.get("/api/accounts/me/")
    assert response.status_code == 401
    assert set(response.json()) == {"detail"}


def test_me_with_a_bad_token(client):
    response = client.get(
        "/api/accounts/me/", headers={"Authorization": "Bearer not-a-token"}
    )
    assert response.status_code == 401
    assert "detail" in response.json()
