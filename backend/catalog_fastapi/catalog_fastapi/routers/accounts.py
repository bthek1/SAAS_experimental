import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from catalog_fastapi import services
from catalog_fastapi.auth import (
    CurrentUser,
    DbSession,
    TokenError,
    authenticate,
    rotate,
    token_pair,
)
from catalog_fastapi.errors import AuthenticationFailed, json_body, parse
from catalog_fastapi.models import User
from catalog_fastapi.schemas import (
    Credentials,
    MePatch,
    RefreshRequest,
    Registration,
    user_out,
)

router = APIRouter()
Body = Annotated[Any, Depends(json_body)]


@router.post("/api/accounts/register/", status_code=201)
def register(session: DbSession, body: Body) -> dict:
    data = parse(Registration, body)
    user = services.create_user(session, data.email, data.password)
    return {"id": str(user.id), "email": user.email}


@router.get("/api/accounts/me/")
def me(user: CurrentUser) -> dict:
    return user_out(user)


@router.patch("/api/accounts/me/")
def patch_me(user: CurrentUser, session: DbSession, body: Body) -> dict:
    data = parse(MePatch, body)
    changes = {name: getattr(data, name) for name in data.model_fields_set}
    return user_out(services.update_user(session, user, changes))


@router.post("/api/token/")
def obtain_token(session: DbSession, body: Body) -> dict:
    data = parse(Credentials, body)
    user = authenticate(session, data.email, data.password)
    if user is None:
        raise AuthenticationFailed("No active account found with the given credentials")
    return token_pair(user)


@router.post("/api/token/refresh/")
def refresh_token(session: DbSession, body: Body) -> dict:
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
    return {"access": access, "refresh": refresh}


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
