"""Owner-scoped questionnaire and battery types (#35).

Another owner's id is 404, never 403, so ids cannot be probed. Lists are newest
first, then by id: bulk-created rows share a `created_at`, and a tie would let a row
repeat or vanish between pages.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from catalog_fastapi import services
from catalog_fastapi.auth import CurrentUser, DbSession
from catalog_fastapi.cache import cached
from catalog_fastapi.errors import NotFound, json_body, parse
from catalog_fastapi.models import BatteryType, QuestionnaireType
from catalog_fastapi.pagination import page_size, paginate
from catalog_fastapi.schemas import (
    BatteryTypeIn,
    BatteryTypePatch,
    QuestionnaireTypeIn,
    QuestionnaireTypePatch,
    battery_type_out,
    questionnaire_type_out,
)

router = APIRouter()
Body = Annotated[Any, Depends(json_body)]

# API writes invalidate these lists at once, so this only bounds admin edits.
TYPE_LIST_CACHE_SECONDS = 5 * 60


def _owned(model, user, session, type_id: uuid.UUID, *, items: bool = False):
    query = select(model).where(model.id == type_id, model.owner_id == user.id)
    if items:
        query = query.options(selectinload(model.items))
    instance = session.scalars(query).one_or_none()
    if instance is None:
        raise NotFound(f"No {model.__name__} matches the given query.")
    return instance


def _list(model, user, session, request: Request, render, *, items: bool = False):
    query = (
        select(model)
        .where(model.owner_id == user.id)
        .order_by(model.created_at.desc(), model.id.desc())
    )
    if items:
        query = query.options(selectinload(model.items))
    return cached(
        "type-list",
        owner_id=user.id,
        params={
            "model": model.__name__,
            "page": request.query_params.get("page", "1"),
            "pageSize": page_size(request),
            # `next` and `previous` are absolute URLs.
            "scheme": request.url.scheme,
            "host": request.headers.get("host", ""),
        },
        ttl=TYPE_LIST_CACHE_SECONDS,
        compute=lambda: paginate(session, request, query, render),
    )


# ── Questionnaire types ────────────────────────────────────────────────────────


@router.get("/api/questionnaire-types/")
def list_questionnaire_types(user: CurrentUser, session: DbSession, request: Request):
    return _list(QuestionnaireType, user, session, request, questionnaire_type_out)


@router.post("/api/questionnaire-types/", status_code=201)
def create_questionnaire_type(user: CurrentUser, session: DbSession, body: Body):
    data = parse(QuestionnaireTypeIn, body)
    qtype = QuestionnaireType(
        owner_id=user.id, title=data.title, questionnaire_json=data.questionnaireJson
    )
    return questionnaire_type_out(services.save_type(session, qtype, owner_id=user.id))


@router.get("/api/questionnaire-types/{type_id}/")
def get_questionnaire_type(user: CurrentUser, session: DbSession, type_id: uuid.UUID):
    return questionnaire_type_out(_owned(QuestionnaireType, user, session, type_id))


@router.patch("/api/questionnaire-types/{type_id}/")
def patch_questionnaire_type(
    user: CurrentUser, session: DbSession, type_id: uuid.UUID, body: Body
):
    qtype = _owned(QuestionnaireType, user, session, type_id)
    data = parse(QuestionnaireTypePatch, body)
    if "title" in data.model_fields_set:
        qtype.title = data.title
    if "questionnaireJson" in data.model_fields_set:
        qtype.questionnaire_json = data.questionnaireJson
    return questionnaire_type_out(services.save_type(session, qtype, owner_id=user.id))


@router.delete("/api/questionnaire-types/{type_id}/", status_code=204)
def delete_questionnaire_type(
    user: CurrentUser, session: DbSession, type_id: uuid.UUID
):
    services.delete_type(session, _owned(QuestionnaireType, user, session, type_id))
    return Response(status_code=204)


# ── Battery types ──────────────────────────────────────────────────────────────


def _battery_out(session, battery: BatteryType) -> dict:
    session.refresh(battery, ["items"])
    return battery_type_out(battery)


@router.get("/api/battery-types/")
def list_battery_types(user: CurrentUser, session: DbSession, request: Request):
    return _list(BatteryType, user, session, request, battery_type_out, items=True)


@router.post("/api/battery-types/", status_code=201)
def create_battery_type(user: CurrentUser, session: DbSession, body: Body):
    data = parse(BatteryTypeIn, body)
    item_ids = services.owned_questionnaire_types(
        session, user.id, data.questionnaireTypeIds
    )
    battery = BatteryType(
        owner_id=user.id, title=data.title, description=data.description
    )
    services.save_type(session, battery, owner_id=user.id, item_ids=item_ids)
    return _battery_out(session, battery)


@router.get("/api/battery-types/{type_id}/")
def get_battery_type(user: CurrentUser, session: DbSession, type_id: uuid.UUID):
    return battery_type_out(_owned(BatteryType, user, session, type_id, items=True))


@router.patch("/api/battery-types/{type_id}/")
def patch_battery_type(
    user: CurrentUser, session: DbSession, type_id: uuid.UUID, body: Body
):
    battery = _owned(BatteryType, user, session, type_id)
    data = parse(BatteryTypePatch, body)
    item_ids = None
    if "questionnaireTypeIds" in data.model_fields_set:
        item_ids = services.owned_questionnaire_types(
            session, user.id, data.questionnaireTypeIds
        )
    if "title" in data.model_fields_set:
        battery.title = data.title
    if "description" in data.model_fields_set:
        battery.description = data.description
    services.save_type(session, battery, owner_id=user.id, item_ids=item_ids)
    return _battery_out(session, battery)


@router.delete("/api/battery-types/{type_id}/", status_code=204)
def delete_battery_type(user: CurrentUser, session: DbSession, type_id: uuid.UUID):
    services.delete_type(session, _owned(BatteryType, user, session, type_id))
    return Response(status_code=204)
