"""Generic error responses: details go to the server log, never to the client."""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")

STALE_MESSAGE = "Someone else changed this record. Reload it and try again."

# Database constraints -> messages a user can act on. Anything unlisted gets a generic one.
CONSTRAINT_MESSAGES = {
    "uq_party_code": "Another record already uses this code",
    "uq_company_single_default": "Another company was made the default at the same time. Reload.",
    "uq_contact_one_primary": "Another contact was made primary at the same time. Reload.",
    "uq_app_user_email": "A user with this email already exists",
    "uq_vendor_code_pair": "This parent/child vendor code pair is already assigned",
}


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

    @app.exception_handler(StaleDataError)
    async def stale(_: Request, __: StaleDataError) -> JSONResponse:
        return JSONResponse({"detail": STALE_MESSAGE}, status_code=409)

    @app.exception_handler(IntegrityError)
    async def integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        diag = getattr(exc.orig, "diag", None)
        constraint = getattr(diag, "constraint_name", None) or ""
        sqlstate = getattr(exc.orig, "sqlstate", "") or ""
        if constraint in CONSTRAINT_MESSAGES:
            return JSONResponse({"detail": CONSTRAINT_MESSAGES[constraint]}, status_code=409)
        log.warning("integrity error sqlstate=%s constraint=%s", sqlstate, constraint)
        if sqlstate == "23505":  # unique_violation
            return JSONResponse(
                {"detail": "This conflicts with an existing record"}, status_code=409
            )
        if sqlstate == "23503":  # foreign_key_violation
            return JSONResponse(
                {"detail": "This refers to, or is used by, another record"}, status_code=409
            )
        return JSONResponse({"detail": "Invalid value"}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        error_id = uuid.uuid4().hex[:12]
        log.exception("unhandled error id=%s path=%s", error_id, request.url.path)
        return JSONResponse({"detail": "Internal error", "error_id": error_id}, status_code=500)
