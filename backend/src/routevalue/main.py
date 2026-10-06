"""FastAPI entry point for RouteValue."""

from fastapi import FastAPI

from routevalue.api.errors import (
    ServiceConfigurationError,
    google_routes_error_handler,
    service_configuration_error_handler,
)
from routevalue.api.routes import router
from routevalue.infrastructure.routing.google_routes import GoogleRoutesError

app = FastAPI(
    title="RouteValue API",
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
