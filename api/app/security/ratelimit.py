"""In-process rate limiting (one API instance; see README known limitations).

The client IP comes from X-Forwarded-For, which uvicorn trusts because the API
is reachable only through the web container's nginx.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings

limiter = Limiter(key_func=get_remote_address, headers_enabled=False)


def auth_limit() -> str:
    return get_settings().auth_rate_limit


def import_limit() -> str:
    return get_settings().import_rate_limit


async def rate_limit_exceeded(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        {"detail": "Too many requests. Try again in a minute."},
        status_code=429,
        headers={"Retry-After": "60"},
    )


__all__ = ["RateLimitExceeded", "auth_limit", "import_limit", "limiter", "rate_limit_exceeded"]
