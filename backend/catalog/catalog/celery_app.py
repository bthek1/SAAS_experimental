"""Celery without Django (#36).

Results stay in Postgres through Celery's own SQLAlchemy backend (tables
`celery_taskmeta` and `celery_tasksetmeta`, which Celery creates). Periodic tasks
are defined here in `beat_schedule`; there are none today. The Django version kept
them in its admin.

    uv run celery -A catalog.celery_app worker --loglevel=info
"""

import logging
import time

from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded

from .settings import get_settings

logger = logging.getLogger(__name__)


def _result_backend() -> str:
    url = get_settings().sqlalchemy_url
    if url in ("sqlite://", "sqlite:///:memory:"):
        # Celery opens its own engine, which would see another empty database.
        return "cache+memory://"
    return f"db+{url}"


settings = get_settings()
app = Celery("catalog")
app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=_result_backend(),
    result_extended=True,
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    timezone="UTC",
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=settings.celery_task_always_eager,
    # Reliability and observability, as the Django version set them.
    task_track_started=True,
    task_send_sent_event=True,
    worker_send_task_events=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=300,
    task_time_limit=360,
    beat_schedule={},
)


@app.task(bind=True)
def debug_task(self) -> str:
    """Log the task request: the smoke test that Celery is wired up."""
    logger.info("debug_task request: %r", self.request)
    return f"debug_task ran: task_id={self.request.id}"


@app.task
def add(x: int, y: int) -> int:
    return x + y


@app.task(bind=True, max_retries=3, default_retry_delay=10)
def process_data(self, payload: dict) -> dict:
    """Process a payload asynchronously. Retries 3 times, 10 s apart."""
    logger.info("process_data started: task_id=%s payload=%s", self.request.id, payload)
    try:
        time.sleep(2)
        result = {"processed": True, "input": payload, "items_count": len(payload)}
    except SoftTimeLimitExceeded:
        logger.warning("process_data soft time limit: task_id=%s", self.request.id)
        raise
    except Exception as exc:
        logger.exception("process_data failed: task_id=%s", self.request.id)
        raise self.retry(exc=exc) from exc
    logger.info("process_data succeeded: task_id=%s", self.request.id)
    return result
