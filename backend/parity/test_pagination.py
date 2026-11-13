"""Every list is `{count, next, previous, results}` with absolute links (#10)."""

import pytest


@pytest.fixture
def thirty(client, owner):  # noqa: ARG001
    return [
        client.post("/api/questionnaire-types/", json={"title": f"t{i:02}"}).json()
        for i in range(30)
    ]


def test_first_page(client, base_url, thirty):
    body = client.get("/api/questionnaire-types/").json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 30
    assert len(body["results"]) == 25
    assert body["next"] == f"{base_url}/api/questionnaire-types/?page=2"
    assert body["previous"] is None
    # Newest first.
    assert [row["id"] for row in body["results"]] == [
        row["id"] for row in reversed(thirty)
    ][:25]
    assert body["results"][0] == thirty[-1]


def test_last_page(client, base_url, thirty):
    body = client.get("/api/questionnaire-types/?page=2").json()
    assert len(body["results"]) == 5
    assert body["next"] is None
    # DRF drops `page=1` from the link to the first page.
    assert body["previous"] == f"{base_url}/api/questionnaire-types/"
    first = client.get("/api/questionnaire-types/").json()["results"]
    seen = {row["id"] for row in first}
    assert seen.isdisjoint(row["id"] for row in body["results"])
    assert len(seen) + 5 == len(thirty)


def test_page_size(client, base_url, thirty):  # noqa: ARG001
    body = client.get("/api/questionnaire-types/?page_size=10&page=2").json()
    assert len(body["results"]) == 10
    assert body["next"] == f"{base_url}/api/questionnaire-types/?page=3&page_size=10"
    assert body["previous"] == f"{base_url}/api/questionnaire-types/?page_size=10"


def test_page_size_is_capped_at_100(client, owner):  # noqa: ARG001
    for i in range(101):
        client.post("/api/battery-types/", json={"title": f"b{i}"})
    body = client.get("/api/battery-types/?page_size=500").json()
    assert body["count"] == 101
    assert len(body["results"]) == 100


@pytest.mark.parametrize("page", ["3", "0", "abc"])
def test_page_out_of_range(client, thirty, page):  # noqa: ARG001
    response = client.get(f"/api/questionnaire-types/?page={page}")
    assert response.status_code == 404
    assert set(response.json()) == {"detail"}


def test_empty_list(client, owner):  # noqa: ARG001
    body = client.get("/api/battery-types/").json()
    assert body == {"count": 0, "next": None, "previous": None, "results": []}
