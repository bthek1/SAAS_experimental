import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from catalog import services
from catalog.auth import (
    CurrentUser,
    DbSession,
    TokenError,
    authenticate,
    rotate,
    token_pair,
)
from catalog.errors import AuthenticationFailed, json_body, parse
from catalog.models import User
from catalog.responses import json_response
from catalog.schemas import (
    Credentials,
    MePatch,
    RefreshRequest,
    Registration,
    user_out,
)

router = APIRouter()
Body = Annotated[Any, Depends(json_body)]


@router.post("/api/accounts/register/", status_code=201)
def register(session: DbSession, body: Body) -> Response:
    data = parse(Registration, body)
    user = services.create_user(session, data.email, data.password)
    return json_response({"id": str(user.id), "email": user.email}, 201)


@router.get("/api/accounts/me/")
def me(user: CurrentUser) -> Response:
    return json_response(user_out(user))


@router.patch("/api/accounts/me/")
def patch_me(user: CurrentUser, session: DbSession, body: Body) -> Response:
    data = parse(MePatch, body)
    changes = {name: getattr(data, name) for name in data.model_fields_set}
    return json_response(user_out(services.update_user(session, user, changes)))


@router.post("/api/token/")
def obtain_token(session: DbSession, body: Body) -> Response:
    data = parse(Credentials, body)
    user = authenticate(session, data.email, data.password)
    if user is None:
        raise AuthenticationFailed("No active account found with the given credentials")
    return json_response(token_pair(user))


@router.post("/api/token/refresh/")
def refresh_token(session: DbSession, body: Body) -> Response:
    data = parse(RefreshRequest, body)
    try:
        claims, access, refresh = rotate(data.refresh)
    except TokenError as exc:
        raise AuthenticationFailed(
            {"detail": str(exc), "code": "token_not_valid"}
        ) from exc
    user = session.get(User, _user_id(claims))
    if user is None or not user.is_active:
        raise AuthenticationFailed(
            {
                "detail": "No active account found for the given token.",
                "code": "no_active_account",
            }
        )
    return json_response({"access": access, "refresh": refresh})


def _user_id(claims: dict) -> uuid.UUID:
    try:
        return uuid.UUID(str(claims.get("user_id")))
    except ValueError:
        raise AuthenticationFailed(
            {
                "detail": "Token contained no recognizable user identification",
                "code": "token_not_valid",
            }
        ) from None
