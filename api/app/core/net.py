import ipaddress

from starlette.requests import Request


def client_ip(request: Request) -> str | None:
    """The caller's IP (already resolved from X-Forwarded-For by uvicorn), or None if
    it isn't a valid address. Never trust it for anything but logging and rate limits."""
    host = request.client.host if request.client else None
    if not host:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None
