"""Kestrel's keep-alive outlasts the gateway's, as gunicorn's does (#24, #44).

Otherwise Kestrel can close an idle connection just as nginx reuses it, and a POST or
PATCH gets a 502. The .NET service sets it in Program.cs; the gateway's upstream
`keepalive_timeout` is in the generated nginx.conf.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
PROGRAM = BACKEND / "instances_NET" / "src" / "Instances.Api" / "Program.cs"


def test_kestrel_keepalive_outlasts_the_gateways() -> None:
    source = PROGRAM.read_text()
    seconds = int(re.search(r"KeepAliveSeconds = (\d+);", source)[1])
    assert "KeepAliveTimeout = TimeSpan.FromSeconds(KeepAliveSeconds)" in source
    nginx = (BACKEND.parent / "infra" / "gateway" / "nginx.conf").read_text()
    timeouts = re.findall(r"keepalive_timeout (\d+)s;", nginx)
    assert timeouts
    assert all(seconds > int(timeout) for timeout in timeouts)
