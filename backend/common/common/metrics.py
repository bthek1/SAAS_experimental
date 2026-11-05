"""Prometheus `/metrics`, for the scraper only (#9).

Served from a middleware at the top of the stack, not a URL: Prometheus
scrapes the app by IP, which is not in ALLOWED_HOSTS, and over plain HTTP,
which prod would redirect. It is deliberately not under /api/.

It answers only a peer inside METRICS_ALLOWED_CIDRS, and never a request that
came through a proxy (any forwarding header), so a reverse proxy in front of
the app cannot make it public. Everyone else gets the same 404 as an unknown
path.
"""

import ipaddress
from functools import cache

from django.conf import settings
from django.http import HttpResponseNotFound
from django.utils.module_loading import import_string
from django_prometheus.exports import ExportToDjangoView

METRICS_PATH = "/metrics"
FORWARDING_HEADERS = ("HTTP_X_FORWARDED_FOR", "HTTP_X_REAL_IP", "HTTP_FORWARDED")


@cache
def _allowed_networks(cidrs: tuple[str, ...]):
    return tuple(ipaddress.ip_network(cidr, strict=False) for cidr in cidrs)


def scrape_allowed(request) -> bool:
    if any(header in request.META for header in FORWARDING_HEADERS):
        return False
    try:
        peer = ipaddress.ip_address(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return False
    networks = _allowed_networks(tuple(settings.METRICS_ALLOWED_CIDRS))
    return any(peer in network for network in networks)


class MetricsEndpointMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.rstrip("/") != METRICS_PATH:
            return self.get_response(request)
        if request.method != "GET" or not scrape_allowed(request):
            return HttpResponseNotFound()
        # A service can update gauges it can only know by asking the database.
        if refresh := getattr(settings, "METRICS_REFRESH", None):
            import_string(refresh)()
        return ExportToDjangoView(request)
