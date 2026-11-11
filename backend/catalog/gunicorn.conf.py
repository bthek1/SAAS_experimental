# gunicorn reads this from the working directory. The shared rules (keepalive above
# the gateway's, multiprocess metrics) are in common/gunicorn_conf.py (#9, #24).
# Run with `-k uvicorn_worker.UvicornWorker`: it passes `keepalive` on to uvicorn.
from common.gunicorn_conf import *  # noqa: F403
