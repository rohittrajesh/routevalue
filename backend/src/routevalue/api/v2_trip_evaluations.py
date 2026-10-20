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
from routevalue.api.eia_pricing_dependencies import (
    build_lazy_eia_pricing_dependencies,
)
from routevalue.api.errors import ServiceConfigurationError
from routevalue.api.preferences import get_user_preferences_repository
from routevalue.api.saved_vehicles import get_saved_vehicle_repository
from routevalue.api.schemas import (
    ApiErrorCode,
    ApiErrorResponse,
    ResolvedLocationInput,
    V2TripEvaluationRequest,
)
from routevalue.api.terrain_status import (
    V2TerrainStatusResponse,
    build_v2_terrain_status,
)
from routevalue.api.terrain_v2_acquisition import (
    build_optional_terrain_acquisition_service,
)
from routevalue.api.terrain_v2_composition import (
    build_terrain_v2_evaluation_service,
)
from routevalue.api.terrain_v2_service import TerrainV2EvaluationService
from routevalue.api.user_identity import (
    get_application_database_engine,
    get_authenticated_user,
)
from routevalue.api.v2_evaluation_mappers import (
    to_v2_trip_evaluation_response,
)
from routevalue.api.v2_evaluation_schemas import V2TripEvaluationResponse
from routevalue.application.authenticated_terrain_trip import NoRoutesAvailableError
from routevalue.application.electric_evaluation import ElectricEvaluationContext
from routevalue.application.gasoline_evaluation import (
    GasolineEvaluationContext,
    UnsupportedVehicleEnergyTypeError,
)
from routevalue.application.gasoline_price_failures import (
    GasolinePriceProviderError,
    GasolinePriceProviderFailureReason,
    GasolinePriceUnavailableError,
    GasolinePriceUnavailableReason,
)
from routevalue.application.gasoline_price_geography import PricingGeographyUnavailableError
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
)
from routevalue.application.profile_trip_evaluation import (
    EnergyInputMismatchError,
    ProfileDrivenTripEvaluationService,
)
from routevalue.domain.identity import SavedVehicleId
from routevalue.domain.models import EnergyPriceQuote
from routevalue.infrastructure.energy.electric import ElectricEnergyCostEstimator
from routevalue.infrastructure.energy.gasoline import GasolineEnergyCostEstimator
from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    EiaPricingPersistenceError,
)
from routevalue.infrastructure.persistence.saved_vehicles import (
    SavedVehiclePersistenceError,
)
from routevalue.infrastructure.persistence.user_preferences import (
    UserPreferencesPersistenceError,
)
from routevalue.infrastructure.routing.google_routes import GoogleRoutesRouteProvider

router = APIRouter(
    prefix="/api/v2/trip-evaluations",
    tags=["V2 Trip Evaluations"],
)


def _build_gasoline_estimator(
    context: GasolineEvaluationContext,
) -> EnergyCostEstimator:
    """Preserve the existing baseline gasoline estimator helper."""
    return GasolineEnergyCostEstimator(
        vehicle=context.vehicle,
        fuel_price_quote=context.fuel_price_quote,
    )


def _build_electric_estimator(
    context: ElectricEvaluationContext,
) -> EnergyCostEstimator:
    """Preserve the existing baseline BEV estimator helper."""
    return ElectricEnergyCostEstimator(
        vehicle=context.vehicle,
        electricity_price_quote=context.electricity_price_quote,
    )


type V2TripEvaluationService = ProfileDrivenTripEvaluationService | TerrainV2EvaluationService


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
) -> V2TripEvaluationService:
    """Compose V2 evaluation with consistent routing and terrain geometry.

    Default mode retains existing overview routing without live elevation
    requests. Explicit live mode couples HIGH_QUALITY route geometry with
    guarded elevation acquisition and the selected quota accounting mode.

    Automatic gasoline pricing reads persisted EIA observations only.
    """
    terrain_service = build_optional_terrain_acquisition_service(
        client=client, engine_factory=get_application_database_engine
    )

    if terrain_service is None:
        route_provider: RouteProvider = GoogleRoutesRouteProvider(
            api_key=api_key,
            client=client,
        )
    else:
        route_provider = GoogleRoutesRouteProvider(
            api_key=api_key,
            client=client,
            polyline_quality="HIGH_QUALITY",
        )

    gasoline_provider, jurisdiction_resolver = build_lazy_eia_pricing_dependencies(
        engine_factory=get_application_database_engine,
    )

    return build_terrain_v2_evaluation_service(
        preferences_repository=preferences_repository,
        saved_vehicle_repository=saved_vehicle_repository,
        route_provider=route_provider,
        terrain_acquisition_service=terrain_service,
        gasoline_price_provider=gasoline_provider,
        gasoline_jurisdiction_resolver=jurisdiction_resolver,
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
            "description": "Required profile or pricing data is unavailable or incompatible.",
        },
        422: {
            "model": ApiErrorResponse,
            "description": "Invalid or conflicting energy price inputs.",
        },
        500: {
            "model": ApiErrorResponse,
            "description": "Server configuration or persisted profile state is invalid.",
        },
        502: {
            "model": ApiErrorResponse,
            "description": "An upstream provider returned an invalid response.",
        },
        503: {
            "model": ApiErrorResponse,
            "description": "An upstream service or pricing data is unavailable.",
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
        V2TripEvaluationService,
        Depends(get_profile_driven_trip_evaluation_service),
    ],
) -> V2TripEvaluationResponse | JSONResponse:
    """Evaluate an authenticated trip and expose actual terrain status."""

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

    if (
        isinstance(service, ProfileDrivenTripEvaluationService)
        and fuel_price_per_gallon is None
        and price_per_kilowatt_hour is None
    ):
        return _error_response(
            status_code=422,
            code=ApiErrorCode.ENERGY_INPUT_MISMATCH,
            detail="An energy price must be supplied for this evaluation.",
        )

    terrain_status: V2TerrainStatusResponse | None = None
    energy_price_quote: EnergyPriceQuote | None = None

    try:
        search_request = _to_route_search_request(request)

        if isinstance(service, TerrainV2EvaluationService):
            outcome = service.evaluate_trip_with_diagnostics(
                user.user_id,
                search_request,
                fuel_price_per_gallon=fuel_price_per_gallon,
                price_per_kilowatt_hour=price_per_kilowatt_hour,
                requested_vehicle_id=requested_vehicle_id,
            )

            result = outcome.evaluation.trip
            energy_price_quote = outcome.energy_price_quote

            terrain_status = build_v2_terrain_status(
                acquisitions=outcome.acquisitions,
                geometry_decision=outcome.geometry_decision,
                terrain_energy=outcome.evaluation.terrain_energy,
            )

        else:
            result = service.evaluate_trip(
                user.user_id,
                search_request,
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

    except PricingGeographyUnavailableError:
        return _error_response(
            status_code=409,
            code=ApiErrorCode.GASOLINE_PRICE_UNAVAILABLE,
            detail=(
                "Automatic gasoline pricing is not available for this "
                "location. Provide a manual gasoline price."
            ),
        )

    except GasolinePriceUnavailableError as exc:
        if exc.reason is GasolinePriceUnavailableReason.PRICE_STALE:
            return _error_response(
                status_code=503,
                code=ApiErrorCode.GASOLINE_PRICE_STALE,
                detail=(
                    "Automatic gasoline pricing is out of date. "
                    "Provide a manual price or try again later."
                ),
            )

        if exc.reason is GasolinePriceUnavailableReason.PROVIDER_UNAVAILABLE:
            return _error_response(
                status_code=503,
                code=ApiErrorCode.GASOLINE_PRICE_PROVIDER_UNAVAILABLE,
                detail=(
                    "Automatic gasoline pricing is temporarily unavailable. "
                    "Provide a manual price or try again later."
                ),
            )

        if exc.reason is GasolinePriceUnavailableReason.INVALID_QUOTE:
            return _error_response(
                status_code=502,
                code=ApiErrorCode.GASOLINE_PRICE_INVALID,
                detail="The gasoline pricing service returned unusable data.",
            )

        return _error_response(
            status_code=409,
            code=ApiErrorCode.GASOLINE_PRICE_UNAVAILABLE,
            detail=(
                "No eligible automatic gasoline price is available "
                "for this vehicle and location. Provide a manual price."
            ),
        )

    except GasolinePriceProviderError as exc:
        if exc.reason is GasolinePriceProviderFailureReason.INVALID_RESPONSE:
            return _error_response(
                status_code=502,
                code=ApiErrorCode.GASOLINE_PRICE_INVALID,
                detail="The gasoline pricing service returned unusable data.",
            )

        return _error_response(
            status_code=503,
            code=ApiErrorCode.GASOLINE_PRICE_PROVIDER_UNAVAILABLE,
            detail=(
                "Automatic gasoline pricing is temporarily unavailable. "
                "Provide a manual price or try again later."
            ),
        )

    except EiaPricingPersistenceError:
        return _error_response(
            status_code=502,
            code=ApiErrorCode.GASOLINE_PRICE_INVALID,
            detail="The gasoline pricing service returned unusable data.",
        )

    except ServiceConfigurationError:
        return _error_response(
            status_code=503,
            code=ApiErrorCode.GASOLINE_PRICE_PROVIDER_UNAVAILABLE,
            detail=(
                "Automatic gasoline pricing is temporarily unavailable. "
                "Provide a manual price or try again later."
            ),
        )

    except NoRoutesAvailableError:
        return _error_response(
            status_code=502,
            code=ApiErrorCode.ROUTING_RESPONSE_INVALID,
            detail="The routing service returned no usable routes.",
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

    return to_v2_trip_evaluation_response(
        result,
        terrain_status=terrain_status,
        energy_price_quote=energy_price_quote,
    )
