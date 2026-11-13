"""`instances` holds no users, so it hears of these as events (#13)."""

from sqlalchemy import func, select

from catalog import services
from catalog.models import BatteryType, QuestionnaireType, User
from catalog.services import save_type

from .test_contracts import assert_same_shape


def types_of(session, user):
    qtype = save_type(
        session, QuestionnaireType(owner_id=user.id, title="Q"), owner_id=user.id
    )
    save_type(
        session,
        BatteryType(owner_id=user.id, title="B"),
        owner_id=user.id,
        item_ids=[qtype.id],
    )


def test_deactivate_and_reactivate(session, user, instances):
    services.update_user(session, user, {"is_active": False})
    services.update_user(session, user, {"is_active": False})
    services.update_user(session, user, {"is_active": True})
    sent = [e["type"] for e in instances.events]
    assert sent == ["user.deactivated", "user.reactivated"]
    first, second = instances.events
    assert second["version"] > first["version"]
    assert_same_shape(first, "event.user.deactivated")
    assert_same_shape(second, "event.user.reactivated")


def test_delete_user_takes_their_types(session, user, instances):
    types_of(session, user)
    instances.events.clear()
    services.delete_user(session, user)
    (event,) = instances.events
    assert event["type"] == "user.deleted"
    assert_same_shape(event, "event.user.deleted")
    for model in (User, QuestionnaireType, BatteryType):
        assert session.scalar(select(func.count()).select_from(model)) == 0


def test_delete_user_leaves_others_alone(session, user, instances):
    from .conftest import make_user

    other = make_user(session)
    types_of(session, other)
    types_of(session, user)
    services.delete_user(session, user)
    assert session.scalar(select(func.count()).select_from(QuestionnaireType)) == 1
    assert session.get(User, other.id) is not None
