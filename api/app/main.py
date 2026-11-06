"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.company.router import router as company_router
from app.config import get_settings
from app.core import logsafety
from app.core.errors import register_error_handlers
from app.customers.router import codes_router as vendor_codes_router
from app.customers.router import router as customers_router
from app.db import get_sessionmaker
from app.health.router import router as health_router
from app.imports.router import router as imports_router
from app.lookups.router import router as lookups_router
from app.parties.router import router as parties_router
from app.pricelists.router import router as pricelists_router
from app.security.csrf import OriginCheckMiddleware
from app.security.headers import SecurityHeadersMiddleware
from app.security.ratelimit import RateLimitExceeded, limiter, rate_limit_exceeded
from app.users.bootstrap import ensure_bootstrap_admin
from app.users.router import router as users_router
from app.vendors.router import router as vendors_router

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    try:
        with get_sessionmaker()() as db:
            ensure_bootstrap_admin(
                db, settings.bootstrap_admin_email, settings.allowed_hosted_domain
            )
    except Exception:
        # The API still starts (health will report the DB); the error is in the log.
        log.exception("bootstrap admin step failed")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    logsafety.install()

    app = FastAPI(
        title="BVT MDM",
        version="0.1.0",
        lifespan=lifespan,
        # No public schema/docs in production.
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded)

    # Starlette runs the last-added middleware first.
    app.add_middleware(OriginCheckMiddleware, allowed_origin=settings.web_origin)
    app.add_middleware(
        SecurityHeadersMiddleware,
        hsts=settings.is_production,
        no_csp_paths=frozenset() if settings.is_production else frozenset({"/api/docs"}),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(lookups_router)
    app.include_router(company_router)
    app.include_router(parties_router)
    app.include_router(customers_router)
    app.include_router(vendor_codes_router)
    app.include_router(vendors_router)
    app.include_router(pricelists_router)
    app.include_router(imports_router)
    return app


app = create_app()
