"""Errors in DRF's shapes, which the SPA reads (#34, #35).

Validation is 400 with `{"field": ["message"]}`, never FastAPI's 422. Every other
error is `{"detail": "..."}`, sometimes with a `code`.
"""

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect


class APIError(Exception):
    status_code = 500
    default_detail = "A server error occurred."

    def __init__(
        self, detail: Any = None, *, headers: dict[str, str] | None = None
    ) -> None:
        self.detail = self.default_detail if detail is None else detail
        self.headers = headers

    def body(self) -> Any:
        return self.detail if isinstance(self.detail, dict) else {"detail": self.detail}


class ParseError(APIError):
    status_code = 400
    default_detail = "Malformed request."


class ValidationError(APIError):
    """`detail` is `{"field": ["message", ...]}`."""

    status_code = 400


class AuthenticationFailed(APIError):
    status_code = 401
    default_detail = "Incorrect authentication credentials."

    def __init__(self, detail: Any = None, **kwargs) -> None:
        kwargs.setdefault("headers", {"WWW-Authenticate": 'Bearer realm="api"'})
        super().__init__(detail, **kwargs)


class NotAuthenticated(AuthenticationFailed):
    default_detail = "Authentication credentials were not provided."


class PermissionDenied(APIError):
    status_code = 403
    default_detail = "You do not have permission to perform this action."


class NotFound(APIError):
    status_code = 404
    default_detail = "Not found."


class InUse(APIError):
    status_code = 409
    default_detail = (
        "This item is used by existing questionnaires or batteries "
        "and cannot be deleted."
    )


class ServiceUnavailable(APIError):
    status_code = 503
    default_detail = "A service this request needs is unavailable. Try again shortly."


REQUIRED = "This field is required."
NOT_NULL = "This field may not be null."


def _message(error: dict) -> str:
    kind, ctx = error["type"], error.get("ctx") or {}
    if kind == "missing":
        return REQUIRED
    if error.get("input") is None and kind != "drf":
        return NOT_NULL
    # A BeforeValidator in front of min_length makes pydantic report the generic
    # `too_short`, not `string_too_short`.
    if kind in ("string_too_short", "too_short"):
        if ctx.get("min_length") == 1:
            return "This field may not be blank."
        return f"Ensure this field has at least {ctx['min_length']} characters."
    if kind == "string_too_long":
        return f"Ensure this field has no more than {ctx['max_length']} characters."
    if kind == "string_type":
        return "Not a valid string."
    if kind == "list_type":
        return (
            f'Expected a list of items but got type "{type(error["input"]).__name__}".'
        )
    if kind == "drf":
        return error["msg"]
    return error["msg"].removeprefix("Value error, ")


def field_errors(exc: PydanticValidationError) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    for error in exc.errors():
        field = str(error["loc"][0]) if error["loc"] else "non_field_errors"
        message = _message(error)
        if message not in errors.setdefault(field, []):
            errors[field].append(message)
    return errors


def parse[M: BaseModel](model: type[M], data: Any) -> M:
    """Validate a JSON body as DRF would: unknown keys ignored, errors per field.

    A PATCH model gives every field an unvalidated default, so an absent key passes
    and `model_fields_set` says which keys were sent.
    """
    if not isinstance(data, dict):
        got = type(data).__name__
        message = f"Invalid data. Expected a dictionary, but got {got}."
        raise ValidationError({"non_field_errors": [message]})
    try:
        return model.model_validate(data)
    except PydanticValidationError as exc:
        raise ValidationError(field_errors(exc)) from exc


async def json_body(request: Request) -> Any:
    """The request body as JSON. An empty body is `{}`, as DRF's `request.data`."""
    raw = await request.body()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise ParseError(f"JSON parse error - {exc}") from exc


def install(app: FastAPI) -> None:
    @app.exception_handler(ClientDisconnect)
    async def _gone(_request: Request, _exc: ClientDisconnect) -> Response:
        # The client left before sending its body (k6 aborting a run). Nobody reads
        # this, but unhandled it logs a traceback per request. 499 as nginx logs it.
        return Response(status_code=499)

    @app.exception_handler(APIError)
    async def _api_error(_request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(exc.body(), exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, _exc: RequestValidationError):
        # Path and query parameters. Bodies go through parse().
        return JSONResponse({"detail": "Not found."}, 404)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 405:
            detail = f'Method "{request.method}" not allowed.'
        elif exc.status_code == 404:
            detail = "Not found."
        else:
            detail = exc.detail
        return JSONResponse(
            {"detail": detail}, exc.status_code, headers=getattr(exc, "headers", None)
        )
