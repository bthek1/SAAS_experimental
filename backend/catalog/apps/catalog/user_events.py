"""User changes `instances` must hear about, since it holds no users (#13)."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.utils import timezone

from . import events


def _version() -> int:
    # Microseconds, not a counter: a saved user instance could overwrite a counter
    # with a stale value, and these events are only ever minutes apart.
    return int(timezone.now().timestamp() * 1_000_000)


def _remember_active(sender, instance, update_fields=None, **kwargs):  # noqa: ARG001
    instance._was_active = None
    if instance._state.adding:
        return
    if update_fields is not None and "is_active" not in update_fields:
        return
    instance._was_active = (
        sender.objects.filter(pk=instance.pk)
        .values_list("is_active", flat=True)
        .first()
    )


def _publish_active_change(sender, instance, created, **kwargs):  # noqa: ARG001
    was_active = getattr(instance, "_was_active", None)
    if created or was_active is None or was_active == instance.is_active:
        return
    action = "reactivated" if instance.is_active else "deactivated"
    with transaction.atomic():
        events.emit(f"user.{action}", instance.pk, _version(), {})


def _publish_deleted(sender, instance, **kwargs):  # noqa: ARG001
    with transaction.atomic():
        events.emit("user.deleted", instance.pk, _version(), {})


def connect() -> None:
    user_model = get_user_model()
    pre_save.connect(_remember_active, sender=user_model, dispatch_uid="user_active_1")
    post_save.connect(
        _publish_active_change, sender=user_model, dispatch_uid="user_active_2"
    )
    post_delete.connect(
        _publish_deleted, sender=user_model, dispatch_uid="user_deleted"
    )
