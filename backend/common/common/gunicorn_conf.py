"""gunicorn settings read from the working directory on every start (#9).

Command-line flags (the Dockerfile's --bind and --workers) still win.

With PROMETHEUS_MULTIPROC_DIR set, every worker writes its metrics to files in
that directory and /metrics adds them up. Without it, each scrape sees only
the one worker that answered it. The directory must start empty, and a dead
worker's files must be marked, or its gauges linger.
"""

import os
import shutil
from pathlib import Path


def on_starting(server):  # noqa: ARG001
    directory = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if directory:
        shutil.rmtree(directory, ignore_errors=True)
        Path(directory).mkdir(parents=True)


def child_exit(server, worker):  # noqa: ARG001
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)
