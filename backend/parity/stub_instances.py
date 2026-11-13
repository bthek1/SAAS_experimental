"""A stand-in for `instances`, over real HTTP, run in a thread of the test process.

It records the events `catalog` sends and answers retire with a status the test sets.
"""

import json
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RETIRE = re.compile(r"^/internal/refs/(?P<kind>[a-z_]+)/(?P<id>[0-9a-f-]+)/retire/$")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class StubInstances:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.retired: list[tuple[str, str]] = []
        self.authorizations: list[str] = []
        self.events_status = 200
        self.retire_status = 204
        self._server = ThreadingHTTPServer(("127.0.0.1", free_port()), self._handler())
        self.url = f"http://127.0.0.1:{self._server.server_port}"

    def events_for(self, aggregate_id: str) -> list[dict]:
        return [event for event in self.events if event["aggregateId"] == aggregate_id]

    def _handler(self):
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def _reply(self, status: int) -> None:
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                stub.authorizations.append(self.headers.get("Authorization", ""))
                if self.path == "/internal/events/":
                    if stub.events_status == 200:
                        stub.events.append(json.loads(body))
                    self._reply(stub.events_status)
                elif match := RETIRE.match(self.path):
                    if stub.retire_status == 204:
                        stub.retired.append((match["kind"], match["id"]))
                    self._reply(stub.retire_status)
                else:
                    self._reply(404)

        return Handler

    def __enter__(self) -> StubInstances:
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
