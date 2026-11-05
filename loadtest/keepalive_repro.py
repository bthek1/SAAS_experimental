#!/usr/bin/env python3
"""Reproduce the gateway's reset on reused upstream connections (#24, Phase 2).

    ssh root@<loadgen> python3 - <gateway-url> --minutes 10 \\
        < loadtest/keepalive_repro.py

nginx keeps idle connections to each service. If the service closes one just as
nginx reuses it, the request is reset. nginx retries an idempotent method, but
returns 502 for a POST or PATCH. This sends bursts of POST and PATCH with gaps
spread over the service's idle timeout, so connections go idle together and some
bursts land on the close. Standard library only, so it runs on the container.

The requests change nothing: an unknown share token (404) and a bad refresh
token (401). Anything else in the output is a failure. Compare the 502s here with
"Connection reset by peer" lines in nginx's error log for the same window.
"""

from __future__ import annotations

import argparse
import collections
import http.client
import ipaddress
import json
import random
import sys
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor

HEADERS = {"Content-Type": "application/json"}


def instances_request() -> tuple[str, str, str]:
    path = f"/api/questionnaires/by-token/{uuid.uuid4()}/submit/"
    return "PATCH", path, "{}"


def catalog_request() -> tuple[str, str, str]:
    return "POST", "/api/token/refresh/", '{"refresh": "x"}'


def send(host: str, port: int, service: str) -> tuple[str, int | str]:
    make = instances_request if service == "instances" else catalog_request
    method, path, body = make()
    connection = http.client.HTTPConnection(host, port, timeout=30)
    try:
        connection.request(method, path, body=body, headers=HEADERS)
        return service, connection.getresponse().status
    except OSError as exc:
        return service, type(exc).__name__
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("gateway", help="the gateway's URL, on a private address")
    parser.add_argument("--minutes", type=float, default=10)
    parser.add_argument("--burst", type=int, default=40, help="requests per service")
    parser.add_argument("--min-gap", type=float, default=2.0)
    parser.add_argument("--max-gap", type=float, default=3.0)
    args = parser.parse_args()

    url = urllib.parse.urlsplit(args.gateway)
    if not ipaddress.ip_address(url.hostname).is_private:
        sys.exit(f"refusing {url.hostname}: only private addresses")

    counts: collections.Counter[tuple[str, int | str]] = collections.Counter()
    services = ["instances", "catalog"] * args.burst
    started = time.time()
    bursts = 0
    with ThreadPoolExecutor(max_workers=len(services)) as pool:
        while time.time() - started < args.minutes * 60:
            results = pool.map(lambda s: send(url.hostname, url.port, s), services)
            counts.update(results)
            bursts += 1
            time.sleep(random.uniform(args.min_gap, args.max_gap))  # noqa: S311

    print(  # noqa: T201
        json.dumps(
            {
                "started": started,
                "ended": time.time(),
                "bursts": bursts,
                "counts": {
                    f"{s} {r}": n for (s, r), n in sorted(counts.items(), key=str)
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
