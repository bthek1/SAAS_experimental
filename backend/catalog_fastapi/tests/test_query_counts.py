"""A hot path's query count must not grow with rows (#9)."""

from contextlib import contextmanager

import pytest
from sqlalchemy import event

from catalog_fastapi.db import get_engine


@contextmanager
def count_queries():
    statements: list[str] = []

    def record(_conn, _cursor, statement, *_args):
        statements.append(statement)

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def add_types(auth, n: int) -> list[str]:
    ids = [
        auth.post("/api/questionnaire-types/", json={"title": f"q{i}"}).json()["id"]
        for i in range(n)
    ]
    for i in range(n):
        auth.post(
            "/api/battery-types/",
            json={"title": f"b{i}", "questionnaireTypeIds": ids[:3]},
        )
    return ids


@pytest.mark.parametrize("path", ["/api/questionnaire-types/", "/api/battery-types/"])
def test_list_queries_do_not_grow(auth, path):
    add_types(auth, 3)
    with count_queries() as few:
        auth.get(path)
    add_types(auth, 20)
    with count_queries() as many:
        auth.get(path)
    assert len(many) == len(few)


def test_detail_queries(auth):
    ids = add_types(auth, 3)
    battery = auth.get("/api/battery-types/").json()["results"][0]["id"]
    with count_queries() as queries:
        auth.get(f"/api/battery-types/{battery}/")
    # user, battery, items
    assert len(queries) == 3
    with count_queries() as queries:
        auth.get(f"/api/questionnaire-types/{ids[0]}/")
    assert len(queries) == 2
