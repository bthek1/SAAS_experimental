"""instances_GO's idle timeout outlasts the gateway's, as Kestrel's does (#24, #52).

Otherwise the server can close an idle connection just as nginx reuses it, and a POST or
PATCH gets a 502. The Go service sets it in internal/server/server.go; the gateway's
upstream `keepalive_timeout` is in the generated nginx.conf.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SERVER = BACKEND / "instances_GO" / "internal" / "server" / "server.go"


def test_go_idle_timeout_outlasts_the_gateways() -> None:
    source = SERVER.read_text()
    seconds = int(re.search(r"const KeepAliveSeconds = (\d+)", source)[1])
    assert "IdleTimeout:       KeepAliveSeconds * time.Second" in source
    nginx = (BACKEND.parent / "infra" / "gateway" / "nginx.conf").read_text()
    timeouts = re.findall(r"keepalive_timeout (\d+)s;", nginx)
    assert timeouts
    assert all(seconds > int(timeout) for timeout in timeouts)
