"""Authenticated V2 profile-driven trip evaluation API."""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from routevalue.api.dependencies import (
    get_google_routes_api_key,
    get_google_routes_http_client,
)
from routevalue.api.preferences import get_user_preferences_repository
from routevalue.api.saved_vehicles import get_saved_vehicle_repository
from routevalue.api.schemas import (
    ApiErrorCode,
    ApiErrorResponse,
    ResolvedLocationInput,
    V2TripEvaluationRequest,
)
from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_evaluation_mappers import (
    to_v2_trip_evaluation_response,
)
from routevalue.api.v2_evaluation_schemas import (
    V2TripEvaluationResponse,
)
from routevalue.application.electric_evaluation import (
    ElectricEvaluationContext,
)
from routevalue.application.gasoline_evaluation import (
    GasolineEvaluationContext,
    UnsupportedVehicleEnergyTypeError,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.models import (
    ResolvedLocation,
    RouteSearchRequest,
)
from routevalue.application.ports import (
    EnergyCostEstimator,
    RouteProvider,
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.application.profile_resolution import (
    ProfileResolutionError,
    ProfileResolutionFailureReason,
    ProfileResolutionService,
)
from routevalue.application.profile_trip_evaluation import (
    EnergyInputMismatchError,
    ProfileDrivenTripEvaluationService,
)
from routevalue.domain.identity import SavedVehicleId
from routevalue.infrastructure.energy.electric import (
    ElectricEnergyCostEstimator,
)
from routevalue.infrastructure.energy.gasoline import (
    GasolineEnergyCostEstimator,
)
from routevalue.infrastructure.persistence.saved_vehicles import (
    SavedVehiclePersistenceError,
)
from routevalue.infrastructure.persistence.user_preferences import (
    UserPreferencesPersistenceError,
)
from routevalue.infrastructure.routing.google_routes import (
    GoogleRoutesRouteProvider,
)

router = APIRouter(
    prefix="/api/v2/trip-evaluations",
    tags=["V2 Trip Evaluations"],
)


def _build_gasoline_estimator(
    context: GasolineEvaluationContext,
) -> EnergyCostEstimator:
    """Compose the existing gasoline estimator from resolved context."""

    return GasolineEnergyCostEstimator(
        vehicle=context.vehicle,
        fuel_price_quote=context.fuel_price_quote,
    )


def _build_electric_estimator(
    context: ElectricEvaluationContext,
) -> EnergyCostEstimator:
    """Compose the baseline BEV estimator from resolved context."""

    return ElectricEnergyCostEstimator(
        vehicle=context.vehicle,
        electricity_price_quote=context.electricity_price_quote,
    )


def get_profile_driven_trip_evaluation_service(
    preferences_repository: Annotated[
        UserPreferencesRepository,
        Depends(get_user_preferences_repository),
    ],
    saved_vehicle_repository: Annotated[
        SavedVehicleRepository,
        Depends(get_saved_vehicle_repository),
    ],
    api_key: Annotated[
        str,
        Depends(get_google_routes_api_key),
    ],
    client: Annotated[
        httpx.Client,
        Depends(get_google_routes_http_client),
    ],
) -> ProfileDrivenTripEvaluationService:
    """Compose authenticated V2 evaluation with both energy models."""

    profile_resolution_service = ProfileResolutionService(
        preferences_repository=preferences_repository,
        saved_vehicle_repository=saved_vehicle_repository,
    )

    route_provider: RouteProvider = GoogleRoutesRouteProvider(
        api_key=api_key,
        client=client,
    )

    return ProfileDrivenTripEvaluationService(
        profile_resolution_service=profile_resolution_service,
        route_provider=route_provider,
        gasoline_estimator_factory=_build_gasoline_estimator,
        electric_estimator_factory=_build_electric_estimator,
    )


def _to_resolved_location(
    location: ResolvedLocationInput,
) -> ResolvedLocation:
    """Map a validated HTTP location to the application model."""

    return ResolvedLocation(
        display_name=location.display_name,
        latitude=location.latitude,
        longitude=location.longitude,
        source=location.source,
        source_id=location.source_id,
    )


def _to_route_search_request(
    request: V2TripEvaluationRequest,
) -> RouteSearchRequest:
    """Map V2 trip-specific inputs without introducing V1 personalization."""

    return RouteSearchRequest(
        origin=_to_resolved_location(request.origin),
        destination=_to_resolved_location(request.destination),
    )


def _error_response(
    *,
    status_code: int,
    code: ApiErrorCode,
    detail: str,
) -> JSONResponse:
    """Return the established flat RouteValue API error shape."""

    return JSONResponse(
        status_code=status_code,
        content={
            "code": code.value,
            "detail": detail,
        },
    )


_PROFILE_FAILURES: dict[
    ProfileResolutionFailureReason,
    tuple[int, str],
] = {
    ProfileResolutionFailureReason.VALUE_OF_TIME_NOT_CONFIGURED: (
        409,
        "Configure your value of time before evaluating a trip.",
    ),
    ProfileResolutionFailureReason.DEFAULT_VEHICLE_NOT_CONFIGURED: (
        409,
        "Select a saved vehicle or configure a default vehicle.",
    ),
    ProfileResolutionFailureReason.DEFAULT_VEHICLE_UNAVAILABLE: (
        409,
        "Your default saved vehicle is no longer available.",
    ),
    ProfileResolutionFailureReason.SAVED_VEHICLE_NOT_FOUND: (
        404,
        "Saved vehicle was not found.",
    ),
}


def _profile_failure_response(
    error: ProfileResolutionError,
) -> JSONResponse:
    """Translate provider-neutral profile failures into HTTP responses."""

    status_code, detail = _PROFILE_FAILURES[error.reason]

    return _error_response(
        status_code=status_code,
        code=ApiErrorCode(error.reason.value),
        detail=detail,
    )


@router.post(
    "",
    response_model=V2TripEvaluationResponse,
    responses={
        401: {
            "model": ApiErrorResponse,
            "description": "Authentication is required.",
        },
        404: {
            "model": ApiErrorResponse,
            "description": "The selected saved vehicle is unavailable.",
        },
        409: {
            "model": ApiErrorResponse,
            "description": "Required profile data or energy input is incompatible.",
        },
        500: {
            "model": ApiErrorResponse,
            "description": "Server configuration or persisted profile state is invalid.",
        },
        502: {
            "model": ApiErrorResponse,
            "description": "The routing service returned an unusable response.",
        },
        503: {
            "model": ApiErrorResponse,
            "description": "An upstream service is temporarily unavailable.",
        },
    },
)
def evaluate_profile_driven_trip(
    request: V2TripEvaluationRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(get_authenticated_user),
    ],
    service: Annotated[
        ProfileDrivenTripEvaluationService,
        Depends(get_profile_driven_trip_evaluation_service),
    ],
) -> V2TripEvaluationResponse | JSONResponse:
    """Evaluate an owned gasoline vehicle or BEV using saved preferences."""

    requested_vehicle_id = (
        SavedVehicleId(value=request.saved_vehicle_id)
        if request.saved_vehicle_id is not None
        else None
    )

    fuel_price_per_gallon = (
        request.gasoline.fuel_price_per_gallon if request.gasoline is not None else None
    )

    price_per_kilowatt_hour = (
        request.electricity.price_per_kilowatt_hour if request.electricity is not None else None
    )

    try:
        result = service.evaluate_trip(
            user.user_id,
            _to_route_search_request(request),
            fuel_price_per_gallon=fuel_price_per_gallon,
            price_per_kilowatt_hour=price_per_kilowatt_hour,
            requested_vehicle_id=requested_vehicle_id,
        )

    except ProfileResolutionError as exc:
        return _profile_failure_response(exc)

    except EnergyInputMismatchError:
        return _error_response(
            status_code=409,
            code=ApiErrorCode.ENERGY_INPUT_MISMATCH,
            detail="The energy price type does not match the selected vehicle.",
        )

    except UnsupportedVehicleEnergyTypeError:
        return _error_response(
            status_code=409,
            code=ApiErrorCode.UNSUPPORTED_VEHICLE_ENERGY_TYPE,
            detail="The selected vehicle has an unsupported energy type.",
        )

    except (
        UserPreferencesPersistenceError,
        SavedVehiclePersistenceError,
    ):
        return _error_response(
            status_code=500,
            code=ApiErrorCode.PROFILE_STATE_INVALID,
            detail="The stored evaluation profile could not be read safely.",
        )

    except SQLAlchemyError:
        return _error_response(
            status_code=503,
            code=ApiErrorCode.PROFILE_SERVICE_UNAVAILABLE,
            detail="Profile storage is temporarily unavailable. Please try again.",
        )

    return to_v2_trip_evaluation_response(result)
