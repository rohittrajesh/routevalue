"""Authenticated RouteValue-owned user profile resource."""

from typing import Annotated

from fastapi import APIRouter, Depends

from routevalue.api.preferences import (
    get_user_preferences_service,
)
from routevalue.api.schemas import (
    ApiErrorResponse,
    UserProfileResponse,
)
from routevalue.api.user_identity import (
    get_authenticated_user,
)
from routevalue.application.identity import (
    AuthenticatedUser,
)
from routevalue.application.preferences import (
    UserPreferences,
)
from routevalue.application.user_preferences import (
    UserPreferencesService,
)

router = APIRouter(
    prefix="/api/v2/me",
    tags=["V2 Profile"],
)


def _preferences_are_configured(
    preferences: UserPreferences,
) -> bool:
    """Report whether the user has any explicit persisted personalization."""

    return (
        preferences.value_of_time_per_hour is not None or preferences.default_vehicle_id is not None
    )


@router.get(
    "",
    response_model=UserProfileResponse,
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
def get_current_user_profile(
    user: Annotated[
        AuthenticatedUser,
        Depends(get_authenticated_user),
    ],
    preferences_service: Annotated[
        UserPreferencesService,
        Depends(get_user_preferences_service),
    ],
) -> UserProfileResponse:
    """Return RouteValue-owned state for the authenticated user."""

    preferences = preferences_service.get_preferences(user.user_id)

    return UserProfileResponse(
        user_id=user.user_id.value,
        preferences_configured=(_preferences_are_configured(preferences)),
        default_vehicle_id=(
            preferences.default_vehicle_id.value
            if preferences.default_vehicle_id is not None
            else None
        ),
    )
