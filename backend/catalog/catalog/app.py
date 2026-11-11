"""The ASGI app (#35).

    uv run uvicorn catalog.app:app --port 8006

Middleware, outermost first: /metrics (before host checks and the HTTPS redirect,
since Prometheus scrapes by IP over plain HTTP), allowed hosts, HTTPS redirect and
HSTS, then CORS.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio.to_thread
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from . import admin, errors
from .db import POOL_OVERFLOW, POOL_SIZE
from .metrics import MetricsMiddleware
from .routers import accounts, internal, types, utils
from .settings import Settings, get_settings

# django-cors-headers' defaults.
CORS_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]
CORS_METHODS = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]


class HttpsMiddleware:
    """Django's SECURE_SSL_REDIRECT and HSTS. /internal/ is exempt: the services
    call each other directly, over a private network."""

    def __init__(self, app: ASGIApp, *, hsts_seconds: int) -> None:
        self.app = app
        self.hsts = f"max-age={hsts_seconds}; includeSubDomains; preload".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["scheme"] == "http" and not scope["path"].startswith("/internal/"):
            host = dict(scope["headers"]).get(b"host", b"").decode()
            query = scope.get("query_string", b"").decode()
            url = f"https://{host}{scope['path']}" + (f"?{query}" if query else "")
            await RedirectResponse(url, status_code=301)(scope, receive, send)
            return

        async def with_hsts(message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(
                    (b"strict-transport-security", self.hsts)
                )
            await send(message)

        await self.app(scope, receive, with_hsts)


def _starlette_hosts(hosts: list[str]) -> list[str]:
    # Django's ".example.com" is Starlette's "*.example.com".
    return [f"*{host}" if host.startswith(".") else host for host in hosts]


@asynccontextmanager
async def _one_thread_per_connection(_app: FastAPI) -> AsyncIterator[None]:
    """Sync endpoints run on AnyIO's threads, 40 by default, against 15 connections.

    With more threads than connections, a burst of slow requests that hold one (k6
    logging every user in at once) leaves the rest waiting on the pool, which fails
    them after 30 s. With one thread per connection they queue for a thread
    instead, as they did on gunicorn's gthread workers (#38).
    """
    anyio.to_thread.current_default_thread_limiter().total_tokens = (
        POOL_SIZE + POOL_OVERFLOW
    )
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="catalog",
        lifespan=_one_thread_per_connection,
        docs_url="/api/docs/" if settings.debug else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.debug else None,
    )
    errors.install(app)
    for module in (accounts, types, utils, internal):
        app.include_router(module.router)
    app.include_router(internal.guarded)
    admin.install(app)

    # Added innermost first.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_origin_regex=settings.cors_allowed_origin_regex or None,
        allow_methods=CORS_METHODS,
        allow_headers=CORS_HEADERS,
        expose_headers=["Content-Disposition"],
        max_age=86400,
    )
    if settings.https_redirect:
        app.add_middleware(HttpsMiddleware, hsts_seconds=settings.hsts_seconds)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=_starlette_hosts(settings.allowed_hosts)
    )
    app.add_middleware(MetricsMiddleware)
    return app


app = create_app()
