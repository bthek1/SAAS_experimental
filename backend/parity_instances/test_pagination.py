"""Every list is `{count, next, previous, results}` with absolute links (#10).

Links are built from the request's Host, which the gateway passes through, so they
point at the gateway rather than the service.
"""

from datetime import datetime

import pytest

from .support import create_battery, create_questionnaire, parse_time

GATEWAY = {"Host": "localhost:8005"}


@pytest.fixture
def thirty(owner, qtype) -> list[dict]:
    return [create_questionnaire(owner, qtype["aggregateId"]) for _ in range(30)]


def page(owner, path: str, **params) -> dict:
    response = owner.http.get(path, params=params, headers=GATEWAY)
    assert response.status_code == 200, response.text
    return response.json()


def order_key(row: dict) -> tuple[datetime, str]:
    return parse_time(row["createdAt"]), row["id"]


def test_first_page(owner, thirty):
    body = page(owner, "/api/questionnaires/")
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 30
    assert len(body["results"]) == 25
    assert body["next"] == "http://localhost:8005/api/questionnaires/?page=2"
    assert body["previous"] is None
    # Newest first.
    assert [row["id"] for row in body["results"]] == [
        row["id"] for row in reversed(thirty)
    ][:25]
    assert body["results"][0] == thirty[-1]


def test_last_page(owner, thirty):
    body = page(owner, "/api/questionnaires/", page=2)
    assert len(body["results"]) == 5
    assert body["next"] is None
    # DRF drops `page=1` from the link to the first page.
    assert body["previous"] == "http://localhost:8005/api/questionnaires/"
    first = {row["id"] for row in page(owner, "/api/questionnaires/")["results"]}
    assert first.isdisjoint(row["id"] for row in body["results"])
    assert len(first) + 5 == len(thirty)


def test_page_size(owner, thirty):  # noqa: ARG001
    body = page(owner, "/api/questionnaires/", page_size=10, page=2)
    assert len(body["results"]) == 10
    assert (
        body["next"] == "http://localhost:8005/api/questionnaires/?page=3&page_size=10"
    )
    assert body["previous"] == "http://localhost:8005/api/questionnaires/?page_size=10"


@pytest.mark.parametrize("size", ["0", "-1", "abc"])
def test_an_unusable_page_size_is_the_default(owner, thirty, size):  # noqa: ARG001
    assert len(page(owner, "/api/questionnaires/", page_size=size)["results"]) == 25


def test_links_keep_the_filters(owner, thirty, qtype):  # noqa: ARG001
    body = page(
        owner,
        "/api/questionnaires/",
        questionnaireType=qtype["aggregateId"],
        page_size=10,
    )
    assert body["count"] == 30
    assert body["next"] == (
        "http://localhost:8005/api/questionnaires/?page=2&page_size=10"
        f"&questionnaireType={qtype['aggregateId']}"
    )


def test_page_size_is_capped_at_100(catalog, owner, qtype):
    # One battery of 101 slots: its questionnaires are created together.
    btype = catalog.btype(owner, [qtype["aggregateId"]] * 101)
    create_battery(owner, btype["aggregateId"])
    body = page(owner, "/api/questionnaires/", page_size=500)
    assert body["count"] == 101
    assert len(body["results"]) == 100


def test_rows_created_together_never_repeat_or_vanish(catalog, owner, qtype):
    # Rows made in one request can share `createdAt`: the order is total anyway.
    btype = catalog.btype(owner, [qtype["aggregateId"]] * 7)
    create_battery(owner, btype["aggregateId"])
    seen = []
    for number in (1, 2, 3):
        results = page(owner, "/api/questionnaires/", page=number, page_size=3)
        seen += results["results"]
    assert len({row["id"] for row in seen}) == len(seen) == 7
    # Newest first, then id, descending.
    assert seen == sorted(seen, key=order_key, reverse=True)


def test_batteries_are_paginated_newest_first(catalog, owner):
    btype = catalog.btype(owner, [])
    made = [create_battery(owner, btype["aggregateId"]) for _ in range(3)]
    body = page(owner, "/api/batteries/", page_size=2)
    assert body["count"] == 3
    assert [row["id"] for row in body["results"]] == [made[2]["id"], made[1]["id"]]
    assert body["next"] == "http://localhost:8005/api/batteries/?page=2&page_size=2"


@pytest.mark.parametrize("number", ["3", "0", "-1", "abc"])
def test_page_out_of_range(owner, thirty, number):  # noqa: ARG001
    response = owner.http.get("/api/questionnaires/", params={"page": number})
    assert response.status_code == 404
    assert set(response.json()) == {"detail"}


@pytest.mark.parametrize("path", ["/api/questionnaires/", "/api/batteries/"])
def test_empty_list(owner, path):
    assert page(owner, path) == {
        "count": 0,
        "next": None,
        "previous": None,
        "results": [],
    }
