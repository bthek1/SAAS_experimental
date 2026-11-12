"""Calls between the services, as `common/peers.py` (#13, #35).

Each direction has its own bearer token. The real client is HTTP. Tests swap it
for `testing.RecordingInstances` with `set_instances_client()`.
"""

import hmac
from functools import cache
from typing import Protocol

import httpx
from fastapi import Request

from .errors import PermissionDenied
from .settings import get_settings


class PeerUnavailable(Exception):
    pass


class RefInUse(Exception):
    pass


class InstancesClient(Protocol):
    def send_event(self, event: dict) -> None: ...
    def retire(self, kind: str, ref_id) -> None: ...


@cache
def http_client() -> httpx.Client:
    """One client per process, shared by its threads.

    `httpx.request()` builds a client, and with it an SSL context, on every call:
    3.6 ms of CPU, and memory that grew by ~140 MiB per worker in a 5-minute run of
    `catalog`'s own traffic (#39). A shared client also keeps connections to
    `instances` open; its 5 s idle expiry is well under `instances`' keepalive.
    """
    return httpx.Client()


def peer_request(method: str, path: str, **kwargs) -> httpx.Response:
    """Call `instances`. PeerUnavailable if it gives no usable answer."""
    settings = get_settings()
    timeout = httpx.Timeout(
        settings.peer_read_timeout, connect=settings.peer_connect_timeout
    )
    headers = {"Authorization": f"Bearer {settings.catalog_to_instances_token}"}
    try:
        response = http_client().request(
            method,
            f"{settings.instances_internal_url}{path}",
            headers=headers,
            timeout=timeout,
            **kwargs,
        )
    except httpx.HTTPError as exc:
        raise PeerUnavailable(f"{method} {path}: {exc}") from exc
    if response.status_code >= 500 or response.status_code in {401, 403}:
        # A refused token is a deployment fault, and retrying can recover from that.
        raise PeerUnavailable(f"{method} {path}: HTTP {response.status_code}")
    return response


class HttpInstances:
    def send_event(self, event: dict) -> None:
        response = peer_request("POST", "/internal/events/", json=event)
        if response.status_code != 200:
            raise ValueError(f"event refused: HTTP {response.status_code}")

    def retire(self, kind: str, ref_id) -> None:
        response = peer_request("POST", f"/internal/refs/{kind}/{ref_id}/retire/")
        if response.status_code == 409:
            raise RefInUse()
        if response.status_code != 204:
            # Fail closed: without a clear yes, nothing gets deleted.
            raise PeerUnavailable(f"retire: HTTP {response.status_code}")


_client: InstancesClient = HttpInstances()


def instances_client() -> InstancesClient:
    return _client


def set_instances_client(client: InstancesClient) -> InstancesClient:
    global _client
    previous, _client = _client, client
    return previous


def require_peer_token(request: Request) -> None:
    """The /internal/ guard: `instances`' token, compared in constant time."""
    expected = get_settings().instances_to_catalog_token
    supplied = request.headers.get("Authorization", "")
    if not expected or not hmac.compare_digest(
        supplied.encode(), f"Bearer {expected}".encode()
    ):
        raise PermissionDenied()
