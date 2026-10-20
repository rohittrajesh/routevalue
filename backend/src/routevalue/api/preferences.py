"""Authenticated V2 API for persistent RouteValue preferences."""

from dataclasses import replace
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from routevalue.api.errors import (
    SavedVehicleNotFoundError,
)
from routevalue.api.saved_vehicles import (
    get_saved_vehicle_repository,
)
from routevalue.api.schemas import (
    ApiErrorResponse,
    PreferredFuelMarketInput,
    UserPreferencesResponse,
    UserPreferencesUpdateRequest,
)
from routevalue.api.user_identity import (
    get_application_database_engine,
    get_authenticated_user,
)
from routevalue.application.identity import (
    AuthenticatedUser,
)
from routevalue.application.ports import (
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.application.preferences import (
    PreferredFuelMarket,
    UserPreferences,
)
from routevalue.application.user_preferences import (
    DefaultVehicleUnavailableError,
    UserDefaultVehicleService,
    UserPreferencesService,
)
from routevalue.domain.identity import (
    SavedVehicleId,
)
from routevalue.infrastructure.persistence.user_preferences import (
    PostgresUserPreferencesRepository,
)

router = APIRouter(
    prefix="/api/v2/preferences",
    tags=["V2 Preferences"],
)


@lru_cache(maxsize=1)
def get_user_preferences_repository() -> UserPreferencesRepository:
    """Build and reuse the production preferences repository."""

    return PostgresUserPreferencesRepository(
        engine=get_application_database_engine(),
    )


def get_user_preferences_service(
    repository: Annotated[
        UserPreferencesRepository,
        Depends(get_user_preferences_repository),
    ],
) -> UserPreferencesService:
    """Compose the preferences application service."""

    return UserPreferencesService(
        repository=repository,
    )


def get_user_default_vehicle_service(
    preferences_repository: Annotated[
        UserPreferencesRepository,
        Depends(get_user_preferences_repository),
    ],
    saved_vehicle_repository: Annotated[
        SavedVehicleRepository,
        Depends(get_saved_vehicle_repository),
    ],
) -> UserDefaultVehicleService:
    """Compose ownership-safe default-vehicle preference behavior."""

    return UserDefaultVehicleService(
        preferences_repository=preferences_repository,
        saved_vehicle_repository=saved_vehicle_repository,
    )


def _to_response(
    preferences: UserPreferences,
) -> UserPreferencesResponse:
    """Map provider-neutral preferences to their public API representation."""

    return UserPreferencesResponse(
        value_of_time_per_hour=(preferences.value_of_time_per_hour),
        default_vehicle_id=(
            preferences.default_vehicle_id.value
            if preferences.default_vehicle_id is not None
            else None
        ),
        electricity_price_per_kwh=preferences.electricity_price_per_kwh,
        preferred_fuel_market=(
            PreferredFuelMarketInput(
                display_name=preferences.preferred_fuel_market.display_name,
                latitude=preferences.preferred_fuel_market.latitude,
                longitude=preferences.preferred_fuel_market.longitude,
            )
            if preferences.preferred_fuel_market is not None
            else None
        ),
    )


@router.get(
    "",
    response_model=UserPreferencesResponse,
    responses={
        401: {
            "model": ApiErrorResponse,
            "description": "Authentication is required.",
        },
        500: {
            "model": ApiErrorResponse,
            "description": ("RouteValue server configuration is unavailable."),
        },
        503: {
            "model": ApiErrorResponse,
            "description": ("Authentication is temporarily unavailable."),
        },
    },
)
def get_preferences(
    user: Annotated[
        AuthenticatedUser,
        Depends(get_authenticated_user),
    ],
    service: Annotated[
        UserPreferencesService,
        Depends(get_user_preferences_service),
    ],
) -> UserPreferencesResponse:
    """Return the authenticated user's persisted preferences."""

    preferences = service.get_preferences(user.user_id)

    return _to_response(preferences)


@router.patch(
    "",
    response_model=UserPreferencesResponse,
    responses={
        401: {
            "model": ApiErrorResponse,
            "description": "Authentication is required.",
        },
        404: {
            "model": ApiErrorResponse,
            "description": ("The requested default saved vehicle is unavailable to this user."),
        },
        500: {
            "model": ApiErrorResponse,
            "description": ("RouteValue server configuration is unavailable."),
        },
        503: {
            "model": ApiErrorResponse,
            "description": ("Authentication is temporarily unavailable."),
        },
    },
)
def update_preferences(
    request: UserPreferencesUpdateRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(get_authenticated_user),
    ],
    preferences_service: Annotated[
        UserPreferencesService,
        Depends(get_user_preferences_service),
    ],
    default_vehicle_service: Annotated[
        UserDefaultVehicleService,
        Depends(get_user_default_vehicle_service),
    ],
) -> UserPreferencesResponse:
    """Atomically apply explicit authenticated preference updates."""

    current = preferences_service.get_preferences(user.user_id)

    value_of_time_per_hour = (
        request.value_of_time_per_hour
        if "value_of_time_per_hour" in request.model_fields_set
        else current.value_of_time_per_hour
    )

    default_vehicle_id = current.default_vehicle_id

    if "default_vehicle_id" in request.model_fields_set:
        requested_default = (
            SavedVehicleId(value=request.default_vehicle_id)
            if request.default_vehicle_id is not None
            else None
        )

        try:
            default_vehicle_service.validate_default_vehicle(
                user.user_id,
                requested_default,
            )

        except DefaultVehicleUnavailableError as exc:
            raise SavedVehicleNotFoundError from exc

        default_vehicle_id = requested_default

    updated = replace(
        current,
        value_of_time_per_hour=(value_of_time_per_hour),
        default_vehicle_id=(default_vehicle_id),
    )
    if "electricity_price_per_kwh" in request.model_fields_set:
        updated = replace(updated, electricity_price_per_kwh=request.electricity_price_per_kwh)
    if "preferred_fuel_market" in request.model_fields_set:
        market = request.preferred_fuel_market
        updated = replace(
            updated,
            preferred_fuel_market=(
                PreferredFuelMarket(market.display_name, market.latitude, market.longitude)
                if market is not None
                else None
            ),
        )

    preferences = preferences_service.save_preferences(
        user.user_id,
        updated,
    )

    return _to_response(preferences)


def close_user_preferences_resources() -> None:
    """Clear cached repositories before the shared engine is disposed."""

    get_user_preferences_repository.cache_clear()
