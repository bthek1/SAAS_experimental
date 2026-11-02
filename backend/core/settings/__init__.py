import os

_env = os.environ.get("SETTINGS", "dev")

if _env == "dev":
    from .dev import *
elif _env == "test":
    from .test import *
elif _env == "prod":
    from .prod import *
elif _env == "loadtest":
    from .loadtest import *
else:
    raise ValueError(
        f"Unknown SETTINGS value: {_env!r}. "
        "Must be 'dev', 'test', 'prod' or 'loadtest'."
    )
