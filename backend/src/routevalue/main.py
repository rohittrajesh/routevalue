"""FastAPI entry point for RouteValue."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routevalue.api.errors import (
    ServiceConfigurationError,
    google_routes_error_handler,
    service_configuration_error_handler,
)
from routevalue.api.routes import router
from routevalue.infrastructure.routing.google_routes import GoogleRoutesError


def _get_cors_origins() -> tuple[str, ...]:
    raw_origins = os.environ.get("ROUTEVALUE_CORS_ORIGINS", "")

    return tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip())


def create_app() -> FastAPI:
    """Create the RouteValue FastAPI application."""

    app = FastAPI(
        title="RouteValue API",
    )

    cors_origins = _get_cors_origins()

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_methods=["POST"],
            allow_headers=["Content-Type"],
        )

    app.add_exception_handler(
        GoogleRoutesError,
        google_routes_error_handler,
    )

    app.add_exception_handler(
        ServiceConfigurationError,
        service_configuration_error_handler,
    )

    app.include_router(router)

    @app.get("/health")
    def health_check() -> dict[str, str]:
        """Report whether the RouteValue API process is available."""

        return {"status": "ok"}

    return app


app = create_app()
