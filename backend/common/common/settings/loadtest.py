"""Load-test settings: production, served over plain HTTP on a private network (#9).

Selected with ``DJANGO_SETTINGS_MODULE=core.settings.loadtest`` (or
``SETTINGS=loadtest``) on the load-test deploy only. ``dev`` and ``prod`` never
import this module.

Everything is ``prod`` except what breaks a plain-HTTP LAN target: the HTTPS
redirect (every k6 request would measure a 301) and the HTTPS-only headers and
cookies. That is only safe off the internet, so the module refuses to load
unless every ``ALLOWED_HOSTS`` entry is a private address.

There are no DRF throttles today. If any are added, raise them here (never in
``base.py``), because every k6 VU shares one client IP.
"""

import ipaddress

from django.core.exceptions import ImproperlyConfigured

from .prod import *

SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False


def with_db_metrics(database: dict) -> dict:
    """Query counts and timings per database, on the Django dashboard."""
    engine = database["ENGINE"].replace(
        "django.db.backends.", "django_prometheus.db.backends.", 1
    )
    return {**database, "ENGINE": engine}


# Lets `seed_loadtest` run against this deploy.
LOADTEST = True

PRIVATE_SUFFIXES = (".lan", ".internal", ".local", ".localhost")


def is_private_host(host: str) -> bool:
    if host == "localhost" or host.endswith(PRIVATE_SUFFIXES):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_private
    except ValueError:
        return False


_public = [host for host in ALLOWED_HOSTS if not is_private_host(host)]
if _public:
    _msg = (
        f"core.settings.loadtest refuses ALLOWED_HOSTS {_public}: the HTTPS "
        "redirect is off here, so it only runs behind private addresses"
    )
    raise ImproperlyConfigured(_msg)
