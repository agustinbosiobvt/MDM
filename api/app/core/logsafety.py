"""Keep secrets out of the logs.

Query strings are dropped from access-log lines: /auth/callback carries Google's one-time
authorization code and the login state, and nothing else in a query string is worth logging.
"""

import logging


def strip_query(path: object) -> object:
    return path.split("?", 1)[0] if isinstance(path, str) else path


class AccessLogQueryFilter(logging.Filter):
    """uvicorn.access records carry (client, method, path, http_version, status)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            record.args = (*args[:2], strip_query(args[2]), *args[3:])
        return True


def install() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, AccessLogQueryFilter) for f in access.filters):
        access.addFilter(AccessLogQueryFilter())
