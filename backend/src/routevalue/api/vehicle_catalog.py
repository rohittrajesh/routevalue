"""Authenticated HTTP browsing for the existing vehicle catalog."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from routevalue.api.saved_vehicles import get_vehicle_specification_provider
from routevalue.api.user_identity import get_authenticated_user
from routevalue.application.ports import VehicleSpecificationProvider

router = APIRouter(
    prefix="/api/v2/vehicle-catalog",
    tags=["V2 Vehicle Catalog"],
    dependencies=[Depends(get_authenticated_user)],
)


class VehicleYearsResponse(BaseModel):
    """Available vehicle model years."""

    years: list[int]


class VehicleMakesResponse(BaseModel):
    """Available makes for a model year."""

    makes: list[str]


class VehicleModelsResponse(BaseModel):
    """Available models for a year and make."""

    models: list[str]


class VehicleCatalogConfigurationResponse(BaseModel):
    """One canonical provider-backed catalog selection."""

    year: int
    make: str
    model: str
    configuration: str
    source: str
    source_id: str


class VehicleConfigurationsResponse(BaseModel):
    """Selectable vehicle configurations."""

    configurations: list[VehicleCatalogConfigurationResponse]


CatalogYear = Annotated[int, Query(ge=1)]
CatalogName = Annotated[str, Query(min_length=1, pattern=r".*\S.*")]


@router.get("/years", response_model=VehicleYearsResponse)
def list_catalog_years(
    provider: Annotated[
        VehicleSpecificationProvider,
        Depends(get_vehicle_specification_provider),
    ],
) -> VehicleYearsResponse:
    """Return available years in provider-defined order."""

    return VehicleYearsResponse(years=list(provider.list_years()))


@router.get("/makes", response_model=VehicleMakesResponse)
def list_catalog_makes(
    year: CatalogYear,
    provider: Annotated[
        VehicleSpecificationProvider,
        Depends(get_vehicle_specification_provider),
    ],
) -> VehicleMakesResponse:
    """Return makes available for a selected model year."""

    return VehicleMakesResponse(
        makes=list(provider.list_makes(year=year)),
    )


@router.get("/models", response_model=VehicleModelsResponse)
def list_catalog_models(
    year: CatalogYear,
    make: CatalogName,
    provider: Annotated[
        VehicleSpecificationProvider,
        Depends(get_vehicle_specification_provider),
    ],
) -> VehicleModelsResponse:
    """Return models available for a selected year and make."""

    return VehicleModelsResponse(
        models=list(
            provider.list_models(
                year=year,
                make=make.strip(),
            )
        ),
    )


@router.get(
    "/configurations",
    response_model=VehicleConfigurationsResponse,
)
def list_catalog_configurations(
    year: CatalogYear,
    make: CatalogName,
    model: CatalogName,
    provider: Annotated[
        VehicleSpecificationProvider,
        Depends(get_vehicle_specification_provider),
    ],
) -> VehicleConfigurationsResponse:
    """Return canonical identities suitable for saved-vehicle creation."""

    configurations = provider.list_configurations(
        year=year,
        make=make.strip(),
        model=model.strip(),
    )

    return VehicleConfigurationsResponse(
        configurations=[
            VehicleCatalogConfigurationResponse(
                year=configuration.year,
                make=configuration.make,
                model=configuration.model,
                configuration=configuration.configuration,
                source=configuration.source,
                source_id=configuration.source_id,
            )
            for configuration in configurations
        ],
    )
