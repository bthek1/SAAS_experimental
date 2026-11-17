"""A stand-in for `catalog`'s `/internal/`, over HTTP, in a thread of the test process.

It serves the snapshots a test puts in `types`, one at a time or as pages, and records
what `instances` asked for. `mode` makes it fail: "404" (no such type), "500", or
"down" (closes the connection without an answer).
"""

import json
import re
import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

SLUGS = {"questionnaire-types": "questionnaire_type", "battery-types": "battery_type"}
ONE = re.compile(r"^/internal/(?P<slug>[a-z-]+)/(?P<id>[0-9a-fA-F-]+)/$")
PAGE = re.compile(r"^/internal/(?P<slug>[a-z-]+)/$")
PAGE_SIZE = 2


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    authorization: str


class StubCatalog:
    def __init__(self) -> None:
        self.types: dict[str, dict] = {}
        self.requests: list[Request] = []
        self.mode = "ok"
        self._server = ThreadingHTTPServer(("127.0.0.1", free_port()), self._handler())
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_port}"

    def reset(self) -> None:
        self.types.clear()
        self.requests.clear()
        self.mode = "ok"

    def add(self, snapshot: dict) -> dict:
        self.types[snapshot["aggregateId"]] = snapshot
        return snapshot

    def asked_for(self, ref_id: str) -> list[Request]:
        return [request for request in self.requests if ref_id in request.path]

    def _page(self, kind: str, after: str | None) -> dict:
        ids = sorted(
            ref_id
            for ref_id, snapshot in self.types.items()
            if snapshot["type"] == f"{kind}.changed"
        )
        if after is not None:
            ids = [ref_id for ref_id in ids if ref_id > after]
        page = ids[:PAGE_SIZE]
        more = len(ids) > PAGE_SIZE
        return {
            "results": [self.types[ref_id] for ref_id in page],
            "next": page[-1] if more else None,
        }

    def _answer(self, path: str) -> tuple[int, dict | None]:
        url = urlsplit(path)
        if match := ONE.match(url.path):
            kind = SLUGS.get(match["slug"])
            snapshot = self.types.get(match["id"].lower())
            if (
                kind is None
                or snapshot is None
                or snapshot["type"] != f"{kind}.changed"
            ):
                return 404, {"detail": "Not found."}
            return 200, snapshot
        if (match := PAGE.match(url.path)) and match["slug"] in SLUGS:
            after = parse_qs(url.query).get("after", [None])[0]
            return 200, self._page(SLUGS[match["slug"]], after)
        return 404, {"detail": "Not found."}

    def _handler(self):
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args) -> None:
                pass

            def do_GET(self) -> None:
                stub.requests.append(
                    Request("GET", self.path, self.headers.get("Authorization", ""))
                )
                if stub.mode == "down":
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                if stub.mode in {"404", "500"}:
                    status, body = int(stub.mode), {"detail": "stub"}
                else:
                    status, body = stub._answer(self.path)
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return Handler

    def __enter__(self) -> StubCatalog:
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
