"""Authenticated V2 API for user-owned saved vehicles."""

from functools import lru_cache
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Response

from routevalue.api.errors import (
    SavedVehicleNotFoundError,
    VehicleConfigurationNotFoundError,
    VehicleSpecificationUnavailableError,
)
from routevalue.api.schemas import ApiErrorResponse
from routevalue.api.user_identity import (
    get_application_database_engine,
    get_authenticated_user,
)
from routevalue.api.vehicle_schemas import (
    ElectricSavedVehicleSpecificationResponse,
    GasolineSavedVehicleSpecificationResponse,
    SavedVehicleCreateRequest,
    SavedVehicleListResponse,
    SavedVehicleResponse,
    VehicleMassResponse,
)
from routevalue.application.identity import (
    AuthenticatedUser,
)
from routevalue.application.models import (
    VehicleCatalogConfiguration,
    VehicleSpecificationUnavailableReason,
)
from routevalue.application.ports import (
    SavedVehicleRepository,
    VehicleSpecificationProvider,
)
from routevalue.application.saved_vehicles import (
    SavedVehicle,
)
from routevalue.application.user_saved_vehicles import (
    UserSavedVehiclesService,
)
from routevalue.domain.identity import (
    SavedVehicleId,
)
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineVehicleSpecification,
)
from routevalue.infrastructure.persistence.saved_vehicles import (
    PostgresSavedVehicleRepository,
)
from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FuelEconomyGovClient,
)
from routevalue.infrastructure.vehicles.fueleconomy_provider import (
    FuelEconomyGovVehicleSpecificationProvider,
)

router = APIRouter(
    prefix="/api/v2/vehicles",
    tags=["V2 Saved Vehicles"],
)


@lru_cache(maxsize=1)
def get_saved_vehicle_repository() -> SavedVehicleRepository:
    """Build and reuse the production saved-vehicle repository."""

    return PostgresSavedVehicleRepository(
        engine=get_application_database_engine(),
    )


@lru_cache(maxsize=1)
def get_vehicle_http_client() -> httpx.Client:
    """Build and reuse the HTTP client used by the vehicle provider."""

    return httpx.Client()


@lru_cache(maxsize=1)
def get_vehicle_specification_provider() -> VehicleSpecificationProvider:
    """Build and reuse the production vehicle specification provider."""

    return FuelEconomyGovVehicleSpecificationProvider(
        client=FuelEconomyGovClient(
            client=get_vehicle_http_client(),
        )
    )


def get_user_saved_vehicles_service(
    repository: Annotated[
        SavedVehicleRepository,
        Depends(get_saved_vehicle_repository),
    ],
    specification_provider: Annotated[
        VehicleSpecificationProvider,
        Depends(get_vehicle_specification_provider),
    ],
) -> UserSavedVehiclesService:
    """Compose the saved-vehicle application service."""

    return UserSavedVehiclesService(
        repository=repository,
        specification_provider=(specification_provider),
    )


def _configuration_from_request(
    request: SavedVehicleCreateRequest,
) -> VehicleCatalogConfiguration:
    """Map a public catalog selection to its provider-neutral model."""

    return VehicleCatalogConfiguration(
        year=request.year,
        make=request.make,
        model=request.model,
        configuration=request.configuration,
        source=request.source,
        source_id=request.source_id,
    )


def _to_response(
    vehicle: SavedVehicle,
) -> SavedVehicleResponse:
    """Map a saved vehicle and its optional mass to the public API."""

    specification = vehicle.specification

    specification_response: (
        GasolineSavedVehicleSpecificationResponse | ElectricSavedVehicleSpecificationResponse
    )

    if isinstance(specification, GasolineVehicleSpecification):
        specification_response = GasolineSavedVehicleSpecificationResponse(
            fuel_grade=specification.fuel_grade.value,
            combined_mpg=specification.combined_mpg,
            city_mpg=specification.city_mpg,
            highway_mpg=specification.highway_mpg,
        )

    elif isinstance(specification, ElectricVehicleSpecification):
        specification_response = ElectricSavedVehicleSpecificationResponse(
            combined_kwh_per_mile=specification.combined_kwh_per_mile,
            city_kwh_per_mile=specification.city_kwh_per_mile,
            highway_kwh_per_mile=specification.highway_kwh_per_mile,
        )

    else:
        raise TypeError("unsupported saved vehicle specification")

    mass = specification.vehicle_mass

    mass_response = (
        VehicleMassResponse(
            kilograms=mass.kilograms,
            source=mass.source,
            source_reference=mass.source_reference,
        )
        if mass is not None
        else None
    )

    return SavedVehicleResponse(
        id=vehicle.id.value,
        year=vehicle.configuration.year,
        make=vehicle.configuration.make,
        model=vehicle.configuration.model,
        configuration=vehicle.configuration.configuration,
        source=vehicle.configuration.source,
        source_id=vehicle.configuration.source_id,
        specification_retrieved_at=vehicle.specification_retrieved_at,
        saved_at=vehicle.saved_at,
        specification=specification_response,
        vehicle_mass=mass_response,
    )


@router.get(
    "",
    response_model=SavedVehicleListResponse,
    responses={
        401: {
            "model": ApiErrorResponse,
        },
        500: {
            "model": ApiErrorResponse,
        },
        503: {
            "model": ApiErrorResponse,
        },
    },
)
def list_saved_vehicles(
    user: Annotated[
        AuthenticatedUser,
        Depends(get_authenticated_user),
    ],
    service: Annotated[
        UserSavedVehiclesService,
        Depends(get_user_saved_vehicles_service),
    ],
) -> SavedVehicleListResponse:
    """Return the authenticated user's saved vehicles."""

    return SavedVehicleListResponse(
        vehicles=[_to_response(vehicle) for vehicle in service.list_vehicles(user.user_id)]
    )


@router.post(
    "",
    response_model=SavedVehicleResponse,
    status_code=201,
    responses={
        401: {
            "model": ApiErrorResponse,
        },
        404: {
            "model": ApiErrorResponse,
        },
        409: {
            "model": ApiErrorResponse,
        },
        500: {
            "model": ApiErrorResponse,
        },
        502: {
            "model": ApiErrorResponse,
        },
        503: {
            "model": ApiErrorResponse,
        },
    },
)
def create_saved_vehicle(
    request: SavedVehicleCreateRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(get_authenticated_user),
    ],
    service: Annotated[
        UserSavedVehiclesService,
        Depends(get_user_saved_vehicles_service),
    ],
) -> SavedVehicleResponse:
    """Revalidate and save one selected catalog configuration."""

    result = service.save_catalog_vehicle(
        user.user_id,
        _configuration_from_request(request),
    )

    if result.saved_vehicle is not None:
        return _to_response(result.saved_vehicle)

    if result.unavailable_reason is VehicleSpecificationUnavailableReason.NOT_FOUND:
        raise VehicleConfigurationNotFoundError

    raise VehicleSpecificationUnavailableError


@router.get(
    "/{vehicle_id}",
    response_model=SavedVehicleResponse,
    responses={
        401: {
            "model": ApiErrorResponse,
        },
        404: {
            "model": ApiErrorResponse,
        },
        500: {
            "model": ApiErrorResponse,
        },
        503: {
            "model": ApiErrorResponse,
        },
    },
)
def get_saved_vehicle(
    vehicle_id: UUID,
    user: Annotated[
        AuthenticatedUser,
        Depends(get_authenticated_user),
    ],
    service: Annotated[
        UserSavedVehiclesService,
        Depends(get_user_saved_vehicles_service),
    ],
) -> SavedVehicleResponse:
    """Return one saved vehicle inside the caller's ownership scope."""

    vehicle = service.get_vehicle(
        user.user_id,
        SavedVehicleId(value=vehicle_id),
    )

    if vehicle is None:
        raise SavedVehicleNotFoundError

    return _to_response(vehicle)


@router.delete(
    "/{vehicle_id}",
    status_code=204,
    response_class=Response,
    responses={
        401: {
            "model": ApiErrorResponse,
        },
        404: {
            "model": ApiErrorResponse,
        },
        500: {
            "model": ApiErrorResponse,
        },
        503: {
            "model": ApiErrorResponse,
        },
    },
)
def delete_saved_vehicle(
    vehicle_id: UUID,
    user: Annotated[
        AuthenticatedUser,
        Depends(get_authenticated_user),
    ],
    service: Annotated[
        UserSavedVehiclesService,
        Depends(get_user_saved_vehicles_service),
    ],
) -> Response:
    """Delete one saved vehicle inside the caller's ownership scope."""

    deleted = service.delete_vehicle(
        user.user_id,
        SavedVehicleId(value=vehicle_id),
    )

    if not deleted:
        raise SavedVehicleNotFoundError

    return Response(status_code=204)


def close_saved_vehicle_resources() -> None:
    """Release cached vehicle API infrastructure."""

    get_saved_vehicle_repository.cache_clear()
    get_vehicle_specification_provider.cache_clear()

    if get_vehicle_http_client.cache_info().currsize:
        client = get_vehicle_http_client()
        client.close()

    get_vehicle_http_client.cache_clear()
