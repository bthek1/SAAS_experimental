#!/usr/bin/env python3
"""The gateway for runs without Docker: same table as nginx, standard library only.

    python3 infra/gateway/dev_router.py --port 8005 \
        --service catalog=http://localhost:8006 --service instances=http://localhost:8007

For dev and e2e only. It keeps the original Host header, as nginx does, so Django
builds links that point back here.
"""

import argparse
import http.client
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROUTES = json.loads((Path(__file__).resolve().parent / "routes.json").read_text())[
    "routes"
]
HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "te", "upgrade"}
NOT_FOUND = b'{"detail":"Not found."}'


def service_for(path: str) -> str | None:
    """The owner of this path, or None: anything not listed stays private."""
    path = urlsplit(path).path
    for route in ROUTES:
        if path.startswith(route["prefix"]):
            return route["service"]
    return None


class Router(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    services: dict[str, str] = {}

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        service = service_for(self.path)
        if service is None:
            self._reply(404, NOT_FOUND)
            return
        target = urlsplit(self.services[service])
        connection = http.client.HTTPConnection(
            target.hostname, target.port, timeout=60
        )
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP
        }
        headers["X-Forwarded-For"] = self.client_address[0]
        try:
            connection.request(self.command, self.path, body, headers)
            upstream = connection.getresponse()
            payload = upstream.read()
        except OSError as exc:
            self._reply(502, json.dumps({"detail": str(exc)}).encode())
            return
        finally:
            connection.close()
        self.send_response(upstream.status)
        for key, value in upstream.getheaders():
            if key.lower() not in HOP_BY_HOP | {"content-length"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _reply(self, status: int, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = do_HEAD = do_OPTIONS = _forward  # noqa: N815

    def log_message(self, format, *args):
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8005)
    parser.add_argument("--service", action="append", default=[])
    options = parser.parse_args()
    Router.services = dict(item.split("=", 1) for item in options.service)
    ThreadingHTTPServer(("0.0.0.0", options.port), Router).serve_forever()  # noqa: S104


if __name__ == "__main__":
    main()
