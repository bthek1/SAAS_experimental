"""The outbox, as seen from a scrape (#13). A stuck one has no other symptom."""

from django.db.models import Min
from django.utils import timezone
from prometheus_client import Counter, Gauge

from .models import OutboxEvent

OUTBOX_PENDING = Gauge(
    "app_outbox_pending_events",
    "Events not yet delivered to instances.",
    multiprocess_mode="livemax",
)
OUTBOX_OLDEST = Gauge(
    "app_outbox_oldest_pending_seconds",
    "Age of the oldest undelivered event. 0 when there are none.",
    multiprocess_mode="livemax",
)
RETIRE_FAILURES = Counter(
    "app_retire_failures_total",
    "Type deletes refused because instances could not be asked.",
)


def refresh() -> None:
    """Called on each scrape. The partial index keeps this cheap."""
    pending = OutboxEvent.objects.filter(delivered_at=None).aggregate(
        oldest=Min("created_at")
    )
    OUTBOX_PENDING.set(OutboxEvent.objects.filter(delivered_at=None).count())
    oldest = pending["oldest"]
    OUTBOX_OLDEST.set((timezone.now() - oldest).total_seconds() if oldest else 0)
