"""Staff admin at /admin/ (#36), on sqladmin.

Admin writes reach `instances` exactly as API writes do: every save, delete and
(de)activation goes through `services.py`, so it records its outbox event and keeps
Django's CASCADE and RESTRICT rules. There is no bulk delete, which would skip the
check with `instances`.

Types are edited here, not created: an owner creates them through the API. A battery
type's items are shown, not edited (sqladmin has no ordered inline); change them
through the API.
"""

import uuid
from collections.abc import Callable

from anyio import to_thread
from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from catalog import services
from catalog.auth import authenticate
from catalog.db import get_engine, session_factory
from catalog.errors import APIError
from catalog.models import BatteryType, OutboxEvent, QuestionnaireType, User
from catalog.settings import get_settings

SESSION_KEY = "admin_user"


async def in_session[T](work: Callable[[Session], T]) -> T:
    """Run sync ORM work in a worker thread, with a session of the app's own."""

    def run() -> T:
        with session_factory()() as session:
            return work(session)

    return await to_thread.run_sync(run)


def _staff(session: Session, user_id: str | None) -> bool:
    if not user_id:
        return False
    user = session.get(User, uuid.UUID(user_id))
    return bool(user and user.is_active and user.is_staff)


class StaffOnly(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        email, password = str(form.get("username", "")), str(form.get("password", ""))

        def check(session: Session) -> str | None:
            user = authenticate(session, email, password)
            return str(user.id) if user and user.is_staff else None

        user_id = await in_session(check)
        if user_id is None:
            return False
        request.session[SESSION_KEY] = user_id
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        # Every request: a staff member removed or deactivated loses access at once.
        user_id = request.session.get(SESSION_KEY)
        return await in_session(lambda session: _staff(session, user_id))


def _readable(exc: APIError) -> ValueError:
    """sqladmin shows `str(exc)` on the list page."""
    detail = exc.detail.get("detail") if isinstance(exc.detail, dict) else exc.detail
    return ValueError(str(detail))


class TypeAdmin(ModelView):
    can_create = False
    column_searchable_list = ["title"]
    column_default_sort = ("created_at", True)
    form_excluded_columns = ["id", "owner_id", "version", "created_at", "updated_at"]

    async def update_model(self, request: Request, pk: str, data: dict):  # noqa: ARG002
        def save(session: Session):
            instance = session.get(self.model, uuid.UUID(pk))
            for name, value in data.items():
                setattr(instance, name, value)
            return services.save_type(session, instance, owner_id=instance.owner_id)

        return await in_session(save)

    async def delete_model(self, request: Request, pk) -> None:  # noqa: ARG002
        def remove(session: Session) -> None:
            services.delete_type(session, session.get(self.model, uuid.UUID(str(pk))))

        try:
            await in_session(remove)
        except APIError as exc:
            raise _readable(exc) from exc


class QuestionnaireTypeAdmin(TypeAdmin, model=QuestionnaireType):
    column_list = ["title", "owner_id", "version", "created_at", "updated_at"]
    form_columns = ["title", "questionnaire_json"]


class BatteryTypeAdmin(TypeAdmin, model=BatteryType):
    column_list = ["title", "owner_id", "version", "created_at", "updated_at"]
    column_details_list = [
        "id",
        "title",
        "description",
        "owner_id",
        "version",
        "items",
        "created_at",
        "updated_at",
    ]
    form_columns = ["title", "description"]


class UserAdmin(ModelView, model=User):
    can_create = False
    column_list = ["email", "is_active", "is_staff", "is_superuser", "date_joined"]
    column_searchable_list = ["email"]
    column_default_sort = ("date_joined", True)
    column_details_exclude_list = ["password"]
    form_columns = [
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "is_superuser",
    ]

    async def update_model(self, request: Request, pk: str, data: dict):  # noqa: ARG002
        def save(session: Session) -> User:
            user = session.get(User, uuid.UUID(pk))
            return services.update_user(session, user, data)

        try:
            return await in_session(save)
        except APIError as exc:
            raise _readable(exc) from exc

    async def delete_model(self, request: Request, pk) -> None:  # noqa: ARG002
        def remove(session: Session) -> None:
            services.delete_user(session, session.get(User, uuid.UUID(str(pk))))

        await in_session(remove)


class OutboxAdmin(ModelView, model=OutboxEvent):
    """Read only: a stuck event has no other symptom than its age here."""

    can_create = False
    can_edit = False
    can_delete = False
    column_list = [
        "event_type",
        "aggregate_id",
        "version",
        "created_at",
        "delivered_at",
        "attempts",
        "last_error",
    ]
    column_default_sort = ("created_at", True)


def install(app: FastAPI) -> Admin:
    admin = Admin(
        app,
        # Its own sessionmaker: sqladmin reconfigures the one it is given.
        session_maker=sessionmaker(bind=get_engine()),
        base_url="/admin",
        title="catalog admin",
        authentication_backend=StaffOnly(secret_key=get_settings().secret_key),
    )
    for view in (UserAdmin, QuestionnaireTypeAdmin, BatteryTypeAdmin, OutboxAdmin):
        admin.add_view(view)
    return admin
