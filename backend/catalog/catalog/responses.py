"""JSON responses that skip FastAPI's `jsonable_encoder` (#41).

An endpoint that returns a dict has FastAPI walk it through `jsonable_encoder`
before encoding it: 2.8 ms of CPU on a 25-item page of types, against 0.25 ms to
encode it directly. Bodies here are already JSON-native (ids and timestamps are
rendered as strings in `schemas.py`), so endpoints return `json_response(...)` and
a cached body goes out as the bytes Redis holds.

Returning a Response bypasses the route decorator's `status_code`, so a create
passes its 201 here too.
"""

import json
from typing import Any

from starlette.responses import Response

MEDIA_TYPE = "application/json"


def dumps(data: Any) -> bytes:
    """Starlette's JSONResponse encoding, so bodies are unchanged byte for byte."""
    return json.dumps(
        data, ensure_ascii=False, allow_nan=False, indent=None, separators=(",", ":")
    ).encode("utf-8")


def json_response(data: Any, status_code: int = 200) -> Response:
    return Response(dumps(data), status_code=status_code, media_type=MEDIA_TYPE)


def raw_json_response(body: bytes, status_code: int = 200) -> Response:
    return Response(body, status_code=status_code, media_type=MEDIA_TYPE)
