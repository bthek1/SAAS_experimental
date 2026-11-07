"""Local copies of `catalog`'s types, and every way they change (#13).

The rules that keep them right:

- An event carries a type's full state and version. Applying one twice changes
  nothing, and an older one is ignored, so duplicates and reordering are harmless.
- `retire_ref` deletes a copy and leaves a tombstone, which stops a late event from
  bringing it back. Here the RESTRICT on the copy is what makes a type in use
  undeletable.
- A synchronous answer from `catalog` is authoritative: the type exists right now.
  That clears a tombstone, which is how a delete that failed after its retire heals.
"""

import logging
from dataclasses import dataclass, field

from common.cache import bump_owner_generation
from common.peers import (
    PeerUnavailable,
    RefInUse,
    ServiceUnavailable,
    catalog_client,
)
from django.db.models import RestrictedError
from django.utils.dateparse import parse_datetime
from prometheus_client import Counter

from .db import atomic
from .models import (
    Battery,
    BatteryTypeRef,
    BatteryTypeRefSlot,
    BlockedOwner,
    Questionnaire,
    QuestionnaireTypeRef,
    RetiredRef,
)

logger = logging.getLogger(__name__)

READ_THROUGHS = Counter(
    "app_ref_read_through_total",
    "Copies fetched from catalog because they had not arrived, by result.",
    ["result"],
)

QUESTIONNAIRE_TYPE = "questionnaire_type"
BATTERY_TYPE = "battery_type"
MODELS = {QUESTIONNAIRE_TYPE: QuestionnaireTypeRef, BATTERY_TYPE: BatteryTypeRef}
KINDS = {model: kind for kind, model in MODELS.items()}

APPLIED = "applied"
IGNORED = "ignored"


def _fields(kind: str, version: int, data: dict) -> dict:
    fields = {
        "owner_id": data["ownerId"],
        "title": data["title"],
        "created_at": parse_datetime(data["createdAt"]),
        "updated_at": parse_datetime(data["updatedAt"]),
        "version": version,
    }
    if kind == QUESTIONNAIRE_TYPE:
        fields["questionnaire_json"] = data["questionnaireJson"]
    else:
        fields["description"] = data["description"]
    return fields


@atomic
def _upsert(kind: str, ref_id, version: int, data: dict) -> str:
    fields = _fields(kind, version, data)
    ref, created = (
        MODELS[kind]
        .objects.select_for_update()
        .get_or_create(pk=ref_id, defaults=fields)
    )
    if not created:
        if ref.version >= version:
            return IGNORED
        for name, value in fields.items():
            setattr(ref, name, value)
        ref.save()
    if kind == BATTERY_TYPE:
        ref.slots.all().delete()
        BatteryTypeRefSlot.objects.bulk_create(
            BatteryTypeRefSlot(
                battery_type=ref,
                questionnaire_type_id=item["questionnaireTypeId"],
                order=item["order"],
            )
            for item in data["items"]
        )
    # Dashboards show titles, and score labels come from the definition.
    bump_owner_generation(ref.owner_id)
    return APPLIED


def _apply_deleted(kind: str, ref_id, version: int) -> str:
    ref = MODELS[kind].objects.filter(pk=ref_id).first()
    if ref is not None:
        if ref.version >= version:
            return IGNORED
        owner_id = ref.owner_id
        try:
            ref.delete()
        except RestrictedError:
            # An instance was created between the retire and the delete, through a
            # read-through. Its answers stay readable; reconcile_refs reports it.
            logger.warning("deleted %s %s still has instances", kind, ref_id)
            return IGNORED
        bump_owner_generation(owner_id)
    RetiredRef.objects.get_or_create(kind=kind, ref_id=ref_id)
    return APPLIED


def _apply_user_event(action: str, owner_id, version: int) -> str:
    row = BlockedOwner.objects.select_for_update().filter(pk=owner_id).first()
    if row is not None and (row.deleted or row.version >= version):
        return IGNORED
    BlockedOwner.objects.update_or_create(
        owner_id=owner_id,
        defaults={
            "blocked": action != "reactivated",
            "deleted": action == "deleted",
            "version": version,
        },
    )
    if action == "deleted":
        # In this order: the copies are RESTRICTed by what is made from them.
        Questionnaire.objects.filter(owner_id=owner_id).delete()
        Battery.objects.filter(owner_id=owner_id).delete()
        for model in MODELS.values():
            model.objects.filter(owner_id=owner_id).delete()
    bump_owner_generation(owner_id)
    return APPLIED


@atomic
def apply_event(event: dict) -> str:
    """Apply one event from `catalog`. Safe to call any number of times."""
    kind, _, action = event["type"].rpartition(".")
    ref_id = event["aggregateId"]
    if kind == "user" and action in {"deactivated", "reactivated", "deleted"}:
        return _apply_user_event(action, ref_id, event["version"])
    if kind not in MODELS or action not in {"changed", "deleted"}:
        raise ValueError(f"unknown event type {event['type']!r}")
    if RetiredRef.objects.filter(kind=kind, ref_id=ref_id).exists():
        return IGNORED
    if action == "deleted":
        return _apply_deleted(kind, ref_id, event["version"])
    # An owner's type event can arrive after the event that deleted the owner.
    if BlockedOwner.objects.filter(pk=event["data"]["ownerId"], deleted=True).exists():
        return IGNORED
    return _upsert(kind, ref_id, event["version"], event["data"])


@atomic
def store_snapshot(snapshot: dict) -> str:
    """Store an authoritative answer from `catalog`, clearing any tombstone."""
    kind = snapshot["type"].rpartition(".")[0]
    ref_id = snapshot["aggregateId"]
    RetiredRef.objects.filter(kind=kind, ref_id=ref_id).delete()
    return _upsert(kind, ref_id, snapshot["version"], snapshot["data"])


def read_through(kind: str, ref_id):
    """The copy, fetched from `catalog`. None if `catalog` has no such type."""
    try:
        snapshot = catalog_client().fetch(kind, ref_id)
    except PeerUnavailable:
        READ_THROUGHS.labels(result="unavailable").inc()
        raise
    READ_THROUGHS.labels(result="found" if snapshot else "missing").inc()
    if snapshot is None:
        return None
    store_snapshot(snapshot)
    return MODELS[kind].objects.get(pk=ref_id)


def read_through_or_503(model, ref_id):
    try:
        return read_through(KINDS[model], ref_id)
    except PeerUnavailable as exc:
        raise ServiceUnavailable() from exc


def ensure_questionnaire_types(ids) -> None:
    """Fetch any of these copies that have not arrived yet."""
    wanted = set(ids)
    present = set(
        QuestionnaireTypeRef.objects.filter(pk__in=wanted).values_list("pk", flat=True)
    )
    for ref_id in wanted - present:
        if read_through_or_503(QuestionnaireTypeRef, ref_id) is None:
            # The slot list is out of date. The battery type's own event will fix it.
            raise ServiceUnavailable()


@atomic
def retire_ref(kind: str, ref_id) -> None:
    """Delete a copy before its source goes. Raises RefInUse if instances use it."""
    ref = MODELS[kind].objects.select_for_update().filter(pk=ref_id).first()
    if ref is not None:
        owner_id = ref.owner_id
        try:
            ref.delete()
        except RestrictedError as exc:
            raise RefInUse() from exc
        bump_owner_generation(owner_id)
    RetiredRef.objects.get_or_create(kind=kind, ref_id=ref_id)


@dataclass
class ReconcileReport:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    orphans_in_use: list[str] = field(default_factory=list)

    @property
    def differences(self) -> int:
        return (
            len(self.created)
            + len(self.updated)
            + len(self.removed)
            + len(self.orphans_in_use)
        )


def _reconcile_kind(kind: str, report: ReconcileReport, *, dry_run: bool) -> None:
    model = MODELS[kind]
    local = dict(model.objects.values_list("pk", "version"))
    seen = set()
    for snapshot in catalog_client().iter_snapshots(kind):
        ref_id = model._meta.pk.to_python(snapshot["aggregateId"])
        seen.add(ref_id)
        label = f"{kind} {ref_id}"
        if ref_id not in local:
            report.created.append(label)
        elif local[ref_id] < snapshot["version"]:
            report.updated.append(label)
        else:
            continue
        if not dry_run:
            store_snapshot(snapshot)

    for ref_id in set(local) - seen:
        label = f"{kind} {ref_id}"
        if model.objects.filter(pk=ref_id, instances__isnull=False).exists():
            report.orphans_in_use.append(label)
            continue
        report.removed.append(label)
        if not dry_run:
            retire_ref(kind, ref_id)


def reconcile(*, dry_run: bool = False) -> ReconcileReport:
    """Rebuild or repair every copy from `catalog`, and say what differed."""
    report = ReconcileReport()
    for kind in MODELS:
        _reconcile_kind(kind, report, dry_run=dry_run)
    return report
