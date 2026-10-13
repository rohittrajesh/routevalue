"""FastAPI entry point for RouteValue."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routevalue.api.authentication import (
    get_authentication_verifier,
)
from routevalue.api.errors import (
    AuthenticationRequiredError,
    AuthenticationServiceUnavailableError,
    SavedVehicleNotFoundError,
    ServiceConfigurationError,
    VehicleConfigurationNotFoundError,
    VehicleSpecificationUnavailableError,
    authentication_required_error_handler,
    authentication_service_unavailable_error_handler,
    fuel_economy_error_handler,
    google_routes_error_handler,
    saved_vehicle_not_found_error_handler,
    service_configuration_error_handler,
    vehicle_configuration_not_found_error_handler,
    vehicle_specification_unavailable_error_handler,
)
from routevalue.api.preferences import (
    close_user_preferences_resources,
)
from routevalue.api.preferences import (
    router as preferences_router,
)
from routevalue.api.profile import (
    router as profile_router,
)
from routevalue.api.routes import router
from routevalue.api.saved_vehicles import (
    close_saved_vehicle_resources,
)
from routevalue.api.saved_vehicles import (
    router as saved_vehicles_router,
)
from routevalue.api.user_identity import (
    close_user_identity_resources,
)
from routevalue.api.v2_trip_evaluations import (
    router as v2_trip_evaluations_router,
)
from routevalue.infrastructure.routing.google_routes import (
    GoogleRoutesError,
)
from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FuelEconomyGovError,
)


def _get_cors_origins() -> tuple[str, ...]:
    raw_origins = os.environ.get(
        "ROUTEVALUE_CORS_ORIGINS",
        "",
    )

    return tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip())


@asynccontextmanager
async def _lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    """Release cached external resources when the API shuts down."""

    del app

    try:
        yield

    finally:
        close_saved_vehicle_resources()
        close_user_preferences_resources()
        close_user_identity_resources()
        get_authentication_verifier.cache_clear()


def create_app() -> FastAPI:
    """Create the RouteValue FastAPI application."""

    app = FastAPI(
        title="RouteValue API",
        lifespan=_lifespan,
    )

    cors_origins = _get_cors_origins()

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_methods=[
                "GET",
                "POST",
                "PATCH",
                "DELETE",
            ],
            allow_headers=[
                "Authorization",
                "Content-Type",
            ],
        )

    app.add_exception_handler(
        AuthenticationRequiredError,
        authentication_required_error_handler,
    )

    app.add_exception_handler(
        AuthenticationServiceUnavailableError,
        authentication_service_unavailable_error_handler,
    )

    app.add_exception_handler(
        SavedVehicleNotFoundError,
        saved_vehicle_not_found_error_handler,
    )

    app.add_exception_handler(
        VehicleConfigurationNotFoundError,
        vehicle_configuration_not_found_error_handler,
    )

    app.add_exception_handler(
        VehicleSpecificationUnavailableError,
        vehicle_specification_unavailable_error_handler,
    )

    app.add_exception_handler(
        FuelEconomyGovError,
        fuel_economy_error_handler,
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

    app.include_router(profile_router)

    app.include_router(preferences_router)

    app.include_router(saved_vehicles_router)

    app.include_router(v2_trip_evaluations_router)

    @app.get("/health")
    def health_check() -> dict[str, str]:
        """Report whether the RouteValue API process is available."""

        return {
            "status": "ok",
        }

    return app


app = create_app()
