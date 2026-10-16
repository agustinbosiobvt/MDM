"""Generic error responses: details go to the server log, never to the client."""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if exc.status_code < 500 else "Internal error"
        return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Field locations and messages only; never echo the submitted input back.
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"detail": "Invalid request", "errors": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        error_id = uuid.uuid4().hex[:12]
        log.exception("unhandled error id=%s path=%s", error_id, request.url.path)
        return JSONResponse({"detail": "Internal error", "error_id": error_id}, status_code=500)
