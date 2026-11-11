"""Prometheus `/metrics`, for the scraper only, as `common/metrics.py` (#9, #35).

Answered by middleware ahead of everything else, and only to a direct peer inside
METRICS_ALLOWED_CIDRS. A request carrying any forwarding header came through a
proxy, so it gets the same 404 as an unknown path: a proxy in front of the service
can never make this public.

Request metrics carry the route template, never the URL, so ids never become label
values. The label is `view` and the buckets are django-prometheus's, so one Grafana
query can add these to `instances`' Django series (#37).
"""

import ipaddress
import os
import time
from functools import cache

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_client import REGISTRY as DEFAULT_REGISTRY
from sqlalchemy import func, select
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from .db import LATENCY_BUCKETS, session_factory
from .models import OutboxEvent, now
from .settings import get_settings

METRICS_PATH = "/metrics"
FORWARDING_HEADERS = (b"x-forwarded-for", b"x-real-ip", b"forwarded")

REQUESTS = Counter(
    "http_requests_total",
    "Requests by route template, method and status.",
    ["view", "method", "status"],
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request latency by route template and method.",
    ["view", "method"],
    buckets=LATENCY_BUCKETS,
)
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


@cache
def _allowed_networks(cidrs: tuple[str, ...]):
    return tuple(ipaddress.ip_network(cidr, strict=False) for cidr in cidrs)


def scrape_allowed(scope: Scope) -> bool:
    if any(name in FORWARDING_HEADERS for name, _ in scope.get("headers", [])):
        return False
    client = scope.get("client")
    try:
        peer = ipaddress.ip_address(client[0] if client else "")
    except ValueError:
        return False
    networks = _allowed_networks(tuple(get_settings().metrics_allowed_cidrs))
    return any(peer in network for network in networks)


def refresh_outbox() -> None:
    """Called on each scrape. The partial index keeps this cheap."""
    with session_factory()() as session:
        pending, oldest = session.execute(
            select(func.count(), func.min(OutboxEvent.created_at)).where(
                OutboxEvent.delivered_at.is_(None)
            )
        ).one()
    OUTBOX_PENDING.set(pending)
    OUTBOX_OLDEST.set((now() - oldest).total_seconds() if oldest else 0)


def _exposition() -> bytes:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry)
    return generate_latest(DEFAULT_REGISTRY)


class MetricsMiddleware:
    """Serves /metrics, and times every other HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["path"].rstrip("/") == METRICS_PATH:
            response: Response
            if scope["method"] != "GET" or not scrape_allowed(scope):
                response = PlainTextResponse("Not Found", status_code=404)
            else:
                refresh_outbox()
                response = Response(_exposition(), media_type=CONTENT_TYPE_LATEST)
            await response(scope, receive, send)
            return

        start = time.perf_counter()
        status = 500

        async def record_status(message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, record_status)
        finally:
            view = getattr(scope.get("route"), "path", "<unmatched>")
            method = scope["method"]
            REQUESTS.labels(view=view, method=method, status=str(status)).inc()
            LATENCY.labels(view=view, method=method).observe(
                time.perf_counter() - start
            )
