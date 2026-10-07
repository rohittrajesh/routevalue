"""Authenticated V2 API for persistent RouteValue preferences."""

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from routevalue.api.schemas import (
    ApiErrorResponse,
    UserPreferencesResponse,
    UserPreferencesUpdateRequest,
)
from routevalue.api.user_identity import (
    get_application_database_engine,
    get_authenticated_user,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.ports import UserPreferencesRepository
from routevalue.application.preferences import UserPreferences
from routevalue.application.user_preferences import (
    UserPreferencesService,
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


def _to_response(
    preferences: UserPreferences,
) -> UserPreferencesResponse:
    """Map provider-neutral preferences to their public API representation."""

    return UserPreferencesResponse(
        value_of_time_per_hour=(preferences.value_of_time_per_hour),
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
            "description": "RouteValue server configuration is unavailable.",
        },
        503: {
            "model": ApiErrorResponse,
            "description": "Authentication is temporarily unavailable.",
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
        500: {
            "model": ApiErrorResponse,
            "description": "RouteValue server configuration is unavailable.",
        },
        503: {
            "model": ApiErrorResponse,
            "description": "Authentication is temporarily unavailable.",
        },
    },
)
def update_preferences(
    request: UserPreferencesUpdateRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(get_authenticated_user),
    ],
    service: Annotated[
        UserPreferencesService,
        Depends(get_user_preferences_service),
    ],
) -> UserPreferencesResponse:
    """Update the authenticated user's persisted value of time."""

    preferences = service.set_value_of_time(
        user.user_id,
        request.value_of_time_per_hour,
    )

    return _to_response(preferences)


def close_user_preferences_resources() -> None:
    """Clear cached repositories before the shared engine is disposed."""

    get_user_preferences_repository.cache_clear()
