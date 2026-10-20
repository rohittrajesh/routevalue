"""Authenticated V2 API for updating saved-vehicle mass."""

from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from routevalue.api.errors import SavedVehicleNotFoundError
from routevalue.api.saved_vehicles import _to_response
from routevalue.api.schemas import ApiErrorResponse
from routevalue.api.user_identity import (
    get_application_database_engine,
    get_authenticated_user,
)
from routevalue.api.vehicle_schemas import SavedVehicleResponse
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.vehicle_mass_update import UserVehicleMassService
from routevalue.domain.identity import SavedVehicleId
from routevalue.domain.vehicle_mass import (
    VehicleMass,
    VehicleMassSource,
    pounds_to_kilograms,
)
from routevalue.infrastructure.persistence.saved_vehicles import (
    PostgresSavedVehicleRepository,
)

router = APIRouter(
    prefix="/api/v2/vehicles",
    tags=["V2 Vehicle Mass"],
)

_MINIMUM_MASS_KG = Decimal(500)
_MAXIMUM_MASS_KG = Decimal(6500)


class VehicleMassUpdateRequest(BaseModel):
    """Set or clear optional, user-entered curb weight.

    No automatic weight lookup is performed. Non-null weight requires a
    unit and source reference and is recorded with user_provided provenance.
    Send weight=null alone to clear it; baseline evaluation remains available.
    """

    model_config = ConfigDict(extra="forbid")

    weight: Decimal | None
    unit: Literal["lb", "kg"] | None = None
    source_reference: str | None = Field(default=None, max_length=512)

    @field_validator("source_reference")
    @classmethod
    def normalize_source_reference(cls, value: str | None) -> str | None:
        """Require a meaningful note whenever a reference is provided."""

        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            raise ValueError("source_reference cannot be blank")

        return normalized

    @model_validator(mode="after")
    def validate_mass_update(self) -> Self:
        """Check units, provenance and plausible mass without using floats."""

        if self.weight is None:
            if self.unit is not None or self.source_reference is not None:
                raise ValueError("clearing mass must not include a unit or source reference")
            return self

        if self.unit is None:
            raise ValueError("a mass unit is required")

        if self.source_reference is None:
            raise ValueError("a source reference is required for user-provided mass")

        if not self.weight.is_finite() or self.weight <= 0:
            raise ValueError("weight must be finite and positive")

        kilograms = pounds_to_kilograms(self.weight) if self.unit == "lb" else self.weight

        if not _MINIMUM_MASS_KG <= kilograms <= _MAXIMUM_MASS_KG:
            raise ValueError("vehicle mass must be between 500 and 6500 kilograms")

        return self

    def to_domain_mass(self) -> VehicleMass | None:
        """Construct the existing domain model with honest provenance."""

        if self.weight is None:
            return None

        if self.unit is None or self.source_reference is None:
            raise ValueError("validated mass inputs are incomplete")

        kilograms = pounds_to_kilograms(self.weight) if self.unit == "lb" else self.weight

        return VehicleMass(
            kilograms=kilograms,
            source=VehicleMassSource.USER_PROVIDED,
            source_reference=self.source_reference,
        )


def get_user_vehicle_mass_service() -> UserVehicleMassService:
    """Reuse the application database without starting a new connection pool."""

    return UserVehicleMassService(
        repository=PostgresSavedVehicleRepository(
            engine=get_application_database_engine(),
        )
    )


@router.patch(
    "/{vehicle_id}/mass",
    response_model=SavedVehicleResponse,
    responses={
        401: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        422: {"description": "Invalid vehicle mass or provenance."},
        500: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
def update_saved_vehicle_mass(
    vehicle_id: UUID,
    request: VehicleMassUpdateRequest,
    user: Annotated[
        AuthenticatedUser,
        Depends(get_authenticated_user),
    ],
    service: Annotated[
        UserVehicleMassService,
        Depends(get_user_vehicle_mass_service),
    ],
) -> SavedVehicleResponse:
    """Update one owned vehicle without changing its catalog efficiency."""

    updated = service.update_mass(
        user.user_id,
        SavedVehicleId(value=vehicle_id),
        request.to_domain_mass(),
    )

    if updated is None:
        raise SavedVehicleNotFoundError

    return _to_response(updated)
