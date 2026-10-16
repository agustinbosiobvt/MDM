"""Security headers applied to every API response."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# The API serves JSON only, so its CSP can be fully locked down.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app: object, *, hsts: bool, no_csp_paths: frozenset[str] = frozenset()
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.hsts = hsts
        # Swagger UI (dev only) loads its assets from a CDN; it is disabled in production.
        self.no_csp_paths = no_csp_paths

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        h = response.headers
        if request.url.path not in self.no_csp_paths:
            h.setdefault("Content-Security-Policy", API_CSP)
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cross-Origin-Resource-Policy"] = "same-origin"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        h.setdefault("Cache-Control", "no-store")
        if self.hsts:
            h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
