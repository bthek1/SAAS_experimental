"""DRF's PageNumberPagination, link for link (#10).

`?page=` and `?page_size=` (default 25, at most 100). Responds `{count, next,
previous, results}` with absolute links built as DRF builds them: the request URL
with `page` replaced, or removed for the first page, and the query keys sorted.
"""

from collections.abc import Callable
from math import ceil
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from .errors import NotFound

PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def page_size(request: Request) -> int:
    try:
        size = int(request.query_params.get("page_size", ""))
    except ValueError:
        return PAGE_SIZE
    return min(size, MAX_PAGE_SIZE) if size > 0 else PAGE_SIZE


def _page_number(request: Request, pages: int) -> int:
    raw = request.query_params.get("page", "1")
    if raw == "last":
        return pages
    try:
        number = int(raw)
    except ValueError:
        raise NotFound("Invalid page.") from None
    if number < 1 or number > pages:
        raise NotFound("Invalid page.")
    return number


def _with_page(url: str, page: int | None) -> str:
    scheme, netloc, path, query, fragment = urlsplit(url)
    params = dict(parse_qsl(query, keep_blank_values=True))
    params.pop("page", None)
    if page is not None:
        params["page"] = str(page)
    return urlunsplit(
        (scheme, netloc, path, urlencode(sorted(params.items())), fragment)
    )


def paginate(
    session: Session, request: Request, query: Select, render: Callable
) -> dict:
    count = session.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    )
    size = page_size(request)
    pages = max(1, ceil(count / size))
    number = _page_number(request, pages)
    rows = session.scalars(query.limit(size).offset((number - 1) * size)).all()
    url = str(request.url)
    return {
        "count": count,
        "next": _with_page(url, number + 1) if number < pages else None,
        "previous": (
            None
            if number == 1
            else _with_page(url, None if number == 2 else number - 1)
        ),
        "results": [render(row) for row in rows],
    }
