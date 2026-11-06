"""Origin check for state-changing requests (first CSRF layer).

The second layer is the double-submit token checked in app.auth.deps for
authenticated requests. SameSite=Lax on the session cookie is the third.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class OriginCheckMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, allowed_origin: str) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.allowed_origin = allowed_origin.rstrip("/")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in UNSAFE_METHODS and not self._same_origin(request):
            return JSONResponse({"detail": "Cross-origin request blocked"}, status_code=403)
        return await call_next(request)

    def _same_origin(self, request: Request) -> bool:
        origin = request.headers.get("origin")
        if origin is not None:
            return origin.rstrip("/") == self.allowed_origin
        # Browsers always send Origin on cross-origin POSTs; fall back to Referer.
        referer = request.headers.get("referer", "")
        return referer == self.allowed_origin or referer.startswith(self.allowed_origin + "/")
