"""In-process peer clients: both apps share this process and database (#13)."""

from collections.abc import Iterator

from apps.catalog import events as catalog_events
from apps.questionnaires import refs


class InProcessInstances:
    def send_event(self, event: dict) -> None:
        refs.apply_event(event)

    def retire(self, kind: str, ref_id) -> None:
        refs.retire_ref(kind, ref_id)


class InProcessCatalog:
    def fetch(self, kind: str, ref_id) -> dict | None:
        return catalog_events.fetch_snapshot(kind, ref_id)

    def iter_snapshots(self, kind: str) -> Iterator[dict]:
        return catalog_events.iter_snapshots(kind)
