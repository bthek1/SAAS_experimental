import logging
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def debug_task(self) -> str:  # type: ignore[override]
    """Log the task request — the canonical smoke test that Celery is wired up.

    Returns the task id so callers (and tests) can assert the task actually ran
    through Celery rather than as a plain function call.
    """
    logger.info("debug_task request: %r", self.request)
    return f"debug_task ran: task_id={self.request.id}"


@shared_task
def add(x: int, y: int) -> int:
    """Simple arithmetic task — used for smoke-testing Celery in dev/test."""
    return x + y


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_data(self, payload: dict) -> dict:  # type: ignore[override]
    """Process arbitrary payload data asynchronously.

    Retries up to 3 times with a 10-second delay on transient errors.
    Raises SoftTimeLimitExceeded if it runs beyond the configured soft limit.
    """
    logger.info("process_data started: task_id=%s payload=%s", self.request.id, payload)
    try:
        # Simulate processing work
        time.sleep(2)
        result = {"processed": True, "input": payload, "items_count": len(payload)}
        logger.info("process_data succeeded: task_id=%s", self.request.id)
        return result
    except SoftTimeLimitExceeded:
        logger.warning(
            "process_data soft time limit exceeded: task_id=%s", self.request.id
        )
        raise
    except Exception as exc:
        logger.exception(
            "process_data failed: task_id=%s error=%s", self.request.id, exc
        )
        raise self.retry(exc=exc) from exc
