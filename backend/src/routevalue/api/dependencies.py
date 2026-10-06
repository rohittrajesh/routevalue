"""Dependency composition for the RouteValue API."""

import os
from collections.abc import Generator
from typing import Annotated

import httpx
from fastapi import Depends

from routevalue.api.errors import ServiceConfigurationError
from routevalue.api.mappers import (
    to_gasoline_vehicle_profile,
    to_user_override_fuel_price_quote,
)
from routevalue.api.schemas import TripEvaluationRequest
from routevalue.application.ports import EnergyCostEstimator, RouteProvider
from routevalue.application.trip_evaluation import TripEvaluationOrchestrator
from routevalue.infrastructure.energy.gasoline import (
    GasolineEnergyCostEstimator,
)
from routevalue.infrastructure.routing.google_routes import (
    GoogleRoutesRouteProvider,
)

_GOOGLE_ROUTES_API_KEY_ENV_VAR = "GOOGLE_ROUTES_API_KEY"


def get_google_routes_api_key() -> str:
    """Load the Google Routes API key from the process environment."""

    api_key = os.getenv(_GOOGLE_ROUTES_API_KEY_ENV_VAR)

    if api_key is None or not api_key.strip():
        raise ServiceConfigurationError(f"{_GOOGLE_ROUTES_API_KEY_ENV_VAR} must be configured")

    return api_key


def get_google_routes_http_client() -> Generator[httpx.Client]:
    """Provide a request-scoped HTTP client for Google Routes."""

    with httpx.Client() as client:
        yield client


def get_trip_evaluation_orchestrator(
    request: TripEvaluationRequest,
    api_key: Annotated[
        str,
        Depends(get_google_routes_api_key),
    ],
    client: Annotated[
        httpx.Client,
        Depends(get_google_routes_http_client),
    ],
) -> TripEvaluationOrchestrator:
    """Build the production orchestrator for one HTTP trip request."""

    route_provider: RouteProvider = GoogleRoutesRouteProvider(
        api_key=api_key,
        client=client,
    )

    energy_cost_estimator: EnergyCostEstimator = GasolineEnergyCostEstimator(
        vehicle=to_gasoline_vehicle_profile(request),
        fuel_price_quote=to_user_override_fuel_price_quote(request),
    )

    return TripEvaluationOrchestrator(
        route_provider=route_provider,
        energy_cost_estimator=energy_cost_estimator,
    )
