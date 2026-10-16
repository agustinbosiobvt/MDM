"""FastAPI application factory."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.errors import register_error_handlers
from app.health.router import router as health_router
from app.security.headers import SecurityHeadersMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="BVT MDM",
        version="0.1.0",
        # No public schema/docs in production.
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )
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
        allow_headers=["Content-Type", "X-CSRF-Token", "If-Match"],
    )
    register_error_handlers(app)
    app.include_router(health_router)
    return app


app = create_app()
