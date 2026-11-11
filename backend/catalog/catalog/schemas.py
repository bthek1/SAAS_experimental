"""Request bodies, validated as DRF validated them, and response shapes (#35).

DRF trims whitespace from every CharField, so these do too. A PATCH model gives
each field an unvalidated `None` default: an absent key passes, and a `null` that
was sent fails as DRF's "may not be null".
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, BaseModel, BeforeValidator, Field
from pydantic_core import PydanticCustomError

from .models import BatteryType, QuestionnaireType, User


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _not_null(value: Any) -> Any:
    if value is None:
        raise PydanticCustomError("drf", "This field may not be null.")
    return value


def _email(value: str) -> str:
    try:
        validate_email(value, check_deliverability=False, test_environment=True)
    except EmailNotValidError as exc:
        raise PydanticCustomError("drf", "Enter a valid email address.") from exc
    return value


def _uuid_list(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    for item in value:
        try:
            uuid.UUID(str(item))
        except ValueError as exc:
            raise PydanticCustomError("drf", f'"{item}" is not a valid UUID.') from exc
    return value


def text(max_length: int, *, blank: bool = False):
    return Annotated[
        str,
        BeforeValidator(_strip),
        Field(min_length=0 if blank else 1, max_length=max_length),
    ]


Email = Annotated[
    str, BeforeValidator(_strip), Field(max_length=254), AfterValidator(_email)
]
AnyJson = Annotated[Any, BeforeValidator(_not_null)]
TypeIds = Annotated[list[str], BeforeValidator(_uuid_list)]


class Registration(BaseModel):
    email: Email
    password: Annotated[str, BeforeValidator(_strip), Field(min_length=8)]


class Credentials(BaseModel):
    email: Annotated[str, BeforeValidator(_strip), Field(min_length=1)]
    password: Annotated[str, Field(min_length=1)]


class RefreshRequest(BaseModel):
    refresh: Annotated[str, BeforeValidator(_strip), Field(min_length=1)]


class MePatch(BaseModel):
    email: Email = None  # type: ignore[assignment]
    first_name: text(150, blank=True) = None  # type: ignore[valid-type]
    last_name: text(150, blank=True) = None  # type: ignore[valid-type]


class QuestionnaireTypeIn(BaseModel):
    title: text(255)  # type: ignore[valid-type]
    questionnaireJson: AnyJson = Field(default_factory=dict)  # noqa: N815


class QuestionnaireTypePatch(BaseModel):
    title: text(255) = None  # type: ignore[valid-type]
    questionnaireJson: AnyJson = None  # noqa: N815


class BatteryTypeIn(BaseModel):
    title: text(255)  # type: ignore[valid-type]
    description: text(10**9, blank=True) = ""  # type: ignore[valid-type]
    questionnaireTypeIds: TypeIds = Field(default_factory=list)  # noqa: N815


class BatteryTypePatch(BaseModel):
    title: text(255) = None  # type: ignore[valid-type]
    description: text(10**9, blank=True) = None  # type: ignore[valid-type]
    questionnaireTypeIds: TypeIds = None  # type: ignore[assignment]  # noqa: N815


# ── Responses ──────────────────────────────────────────────────────────────────


def drf_time(value: datetime) -> str:
    """DRF's DateTimeField: ISO 8601, with UTC written as `Z`."""
    iso = value.isoformat()
    return iso.removesuffix("+00:00") + "Z" if iso.endswith("+00:00") else iso


def user_out(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "date_joined": drf_time(user.date_joined),
    }


def questionnaire_type_out(qtype: QuestionnaireType) -> dict:
    return {
        "id": str(qtype.id),
        "title": qtype.title,
        "questionnaireJson": qtype.questionnaire_json,
        "createdAt": drf_time(qtype.created_at),
        "updatedAt": drf_time(qtype.updated_at),
    }


def battery_type_out(battery: BatteryType) -> dict:
    return {
        "id": str(battery.id),
        "title": battery.title,
        "description": battery.description,
        "createdAt": drf_time(battery.created_at),
        "updatedAt": drf_time(battery.updated_at),
        "questionnaireTypeIds": [
            str(item.questionnaire_type_id) for item in battery.items
        ],
    }
