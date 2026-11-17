"""How one service asks the other for something, and how that can fail (#13).

Each side reaches its peer through a client class named in settings, so neither
imports the other: `INSTANCES_CLIENT` for catalog, `CATALOG_CLIENT` for instances.
"""

import hmac

import httpx
from django.conf import settings
from django.utils.module_loading import import_string
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView


class PeerUnavailable(Exception):
    """The peer could not be reached, or did not give a usable answer."""


class RefInUse(Exception):
    """A copy of this type still has instances, so it cannot be retired."""


class ServiceUnavailable(APIException):
    status_code = 503
    default_detail = "This action is temporarily unavailable. Please try again."
    default_code = "service_unavailable"


def instances_client():
    return import_string(settings.INSTANCES_CLIENT)()


def catalog_client():
    return import_string(settings.CATALOG_CLIENT)()


class InternalToken(BasePermission):
    """The other service's bearer token, one per direction (#13)."""

    def has_permission(self, request, view):  # noqa: ARG002
        expected = settings.PEER_INBOUND_TOKEN
        supplied = request.headers.get("Authorization", "")
        return bool(expected) and hmac.compare_digest(
            supplied.encode(), f"Bearer {expected}".encode()
        )


class InternalView(APIView):
    """Reached only between services: the gateway never routes `/internal/`."""

    authentication_classes = []
    permission_classes = [InternalToken]


def peer_request(method: str, base_url: str, path: str, **kwargs) -> httpx.Response:
    """Call the other service. PeerUnavailable if it gives no usable answer."""
    timeout = httpx.Timeout(
        settings.PEER_READ_TIMEOUT, connect=settings.PEER_CONNECT_TIMEOUT
    )
    headers = {"Authorization": f"Bearer {settings.PEER_OUTBOUND_TOKEN}"}
    try:
        response = httpx.request(
            method, f"{base_url}{path}", headers=headers, timeout=timeout, **kwargs
        )
    except httpx.HTTPError as exc:
        raise PeerUnavailable(f"{method} {path}: {exc}") from exc
    if response.status_code >= 500 or response.status_code in {401, 403}:
        # A refused token is a deployment fault, and retrying can recover from that.
        raise PeerUnavailable(f"{method} {path}: HTTP {response.status_code}")
    return response
