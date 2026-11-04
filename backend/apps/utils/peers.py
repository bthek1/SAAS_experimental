"""How one service asks the other for something, and how that can fail (#13).

Each side reaches its peer through a client class named in settings, so neither
imports the other: `INSTANCES_CLIENT` for catalog, `CATALOG_CLIENT` for instances.
"""

from django.conf import settings
from django.utils.module_loading import import_string
from rest_framework.exceptions import APIException


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
