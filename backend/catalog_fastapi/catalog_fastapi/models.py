"""The tables Django's `catalog` created, mapped as they are (#35).

Names of tables, indexes and constraints are Django's, so Alembic's baseline is the
schema already in `catalogdb` and either implementation can run on it. Foreign keys
are DEFERRABLE INITIALLY DEFERRED, as Django makes them on Postgres. Django's
`on_delete` (CASCADE, RESTRICT) is not in the database: `services.py` does it.

Two Django tables are left out: the user's group and permission links point at
`auth_*` tables this service does not have. `services.delete_user` clears them.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONType = JSON().with_variant(JSONB(), "postgresql")
# SQLite only gives an INTEGER PRIMARY KEY its own ids.
BigId = BigInteger().with_variant(Integer(), "sqlite")


def now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Aware UTC datetimes in and out, whatever the connection's time zone.

    SQLite stores them naive, so they come back as UTC. Events and responses print
    them as `+00:00` and `Z`, so an aware value in another zone would change them.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ARG002
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime")
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):  # noqa: ARG002
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def owner_fk(name: str):
    return ForeignKey(
        "accounts_customuser.id", name=name, deferrable=True, initially="DEFERRED"
    )


class Base(DeclarativeBase):
    pass


# Django's links from a user to `auth_group` and `auth_permission`. Outside
# Base.metadata: this service never creates them, and only deletes from them.
_django_only = MetaData()
DJANGO_USER_LINKS = tuple(
    Table(name, _django_only, Column("customuser_id", Uuid))
    for name in ("accounts_customuser_groups", "accounts_customuser_user_permissions")
)


class User(Base):
    __tablename__ = "accounts_customuser"
    __table_args__ = (
        UniqueConstraint("email", name="accounts_customuser_email_4fd8e7ce_uniq"),
        Index(
            "accounts_customuser_email_4fd8e7ce_like",
            "email",
            postgresql_ops={"email": "varchar_pattern_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    password: Mapped[str] = mapped_column(String(128))
    last_login: Mapped[datetime | None] = mapped_column(UTCDateTime)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    first_name: Mapped[str] = mapped_column(String(150), default="")
    last_name: Mapped[str] = mapped_column(String(150), default="")
    email: Mapped[str] = mapped_column(String(254))
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    date_joined: Mapped[datetime] = mapped_column(UTCDateTime, default=now)

    def __str__(self) -> str:
        return self.email


class QuestionnaireType(Base):
    __tablename__ = "questionnaires_questionnairetype"
    __table_args__ = (
        Index("questionnai_owner_i_be24a4_idx", "owner_id", text("created_at DESC")),
        Index("questionnaires_questionnairetype_owner_id_33ca2bd1", "owner_id"),
        CheckConstraint(
            "version >= 0", name="questionnaires_questionnairetype_version_check"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    title: Mapped[str] = mapped_column(String(255))
    questionnaire_json: Mapped[dict] = mapped_column(JSONType, default=dict)
    # Raised under a row lock on every write. See events.record_change.
    version: Mapped[int] = mapped_column(BigInteger, default=0)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, owner_fk("questionnaires_quest_owner_id_33ca2bd1_fk_accounts_")
    )

    def __str__(self) -> str:
        return self.title


class BatteryType(Base):
    __tablename__ = "questionnaires_batterytype"
    __table_args__ = (
        Index("questionnai_owner_i_8141dc_idx", "owner_id", text("created_at DESC")),
        Index("questionnaires_batterytype_owner_id_37d17dd4", "owner_id"),
        CheckConstraint(
            "version >= 0", name="questionnaires_batterytype_version_check"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(BigInteger, default=0)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, owner_fk("questionnaires_batte_owner_id_37d17dd4_fk_accounts_")
    )
    # Read only. A flush inserts before it deletes, which would break the unique
    # (battery_type_id, order) on a reorder, so services.py writes items itself.
    items: Mapped[list[BatteryTypeItem]] = relationship(
        order_by="BatteryTypeItem.order", viewonly=True
    )

    def __str__(self) -> str:
        return self.title


class BatteryTypeItem(Base):
    __tablename__ = "questionnaires_batterytypeitem"
    __table_args__ = (
        UniqueConstraint(
            "battery_type_id",
            "order",
            name="questionnaires_batteryty_battery_type_id_order_dcdbcc78_uniq",
        ),
        Index(
            "questionnaires_batterytypeitem_battery_type_id_fd206f4c",
            "battery_type_id",
        ),
        Index(
            "questionnaires_batterytypeitem_questionnaire_type_id_7c7803cd",
            "questionnaire_type_id",
        ),
        CheckConstraint(
            '"order" >= 0', name="questionnaires_batterytypeitem_order_check"
        ),
    )

    id: Mapped[int] = mapped_column(BigId, Identity(), primary_key=True)
    order: Mapped[int] = mapped_column(Integer)
    battery_type_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "questionnaires_batterytype.id",
            name="questionnaires_batte_battery_type_id_fd206f4c_fk_questionn",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    questionnaire_type_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "questionnaires_questionnairetype.id",
            name="questionnaires_batte_questionnaire_type_i_7c7803cd_fk_questionn",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    def __str__(self) -> str:
        return f"{self.order}: {self.questionnaire_type_id}"


class OutboxEvent(Base):
    """A change waiting to reach `instances`, committed with the change itself."""

    __tablename__ = "catalog_outboxevent"
    __table_args__ = (
        Index(
            "outbox_pending",
            "created_at",
            postgresql_where=text("delivered_at IS NULL"),
            sqlite_where=text("delivered_at IS NULL"),
        ),
        CheckConstraint("version >= 0", name="catalog_outboxevent_version_check"),
        CheckConstraint("attempts >= 0", name="catalog_outboxevent_attempts_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(64))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(BigInteger)
    data: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")

    def envelope(self) -> dict:
        return {
            "id": str(self.id),
            "type": self.event_type,
            "aggregateId": str(self.aggregate_id),
            "version": self.version,
            "data": self.data,
        }
