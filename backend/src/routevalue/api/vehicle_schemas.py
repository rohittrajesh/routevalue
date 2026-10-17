"""HTTP schemas for authenticated RouteValue saved vehicles."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from routevalue.domain.vehicle_mass import VehicleMassSource


class SavedVehicleCreateRequest(BaseModel):
    """Catalog identity selected by an authenticated user."""

    model_config = {"extra": "forbid"}

    year: int = Field(ge=1)
    make: str
    model: str
    configuration: str
    source: str
    source_id: str

    @field_validator(
        "make",
        "model",
        "configuration",
        "source",
        "source_id",
    )
    @classmethod
    def catalog_value_cannot_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("vehicle catalog values cannot be blank")
        return value


class GasolineSavedVehicleSpecificationResponse(BaseModel):
    """Persisted gasoline energy specification."""

    powertrain: Literal["gasoline"] = "gasoline"
    fuel_grade: Literal["regular", "midgrade", "premium"]
    combined_mpg: Decimal
    city_mpg: Decimal | None
    highway_mpg: Decimal | None


class ElectricSavedVehicleSpecificationResponse(BaseModel):
    """Persisted battery-electric energy specification."""

    powertrain: Literal["bev"] = "bev"
    combined_kwh_per_mile: Decimal
    city_kwh_per_mile: Decimal | None
    highway_kwh_per_mile: Decimal | None


class VehicleMassResponse(BaseModel):
    """Mass and its provenance, without claiming independent verification."""

    kilograms: Decimal
    source: VehicleMassSource
    source_reference: str | None


class SavedVehicleResponse(BaseModel):
    """Public representation of one user-owned vehicle snapshot."""

    id: UUID
    year: int
    make: str
    model: str
    configuration: str
    source: str
    source_id: str
    specification_retrieved_at: datetime
    saved_at: datetime
    specification: (
        GasolineSavedVehicleSpecificationResponse | ElectricSavedVehicleSpecificationResponse
    )
    vehicle_mass: VehicleMassResponse | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class SavedVehicleListResponse(BaseModel):
    """Authenticated user's saved vehicle collection."""

    vehicles: list[SavedVehicleResponse]
