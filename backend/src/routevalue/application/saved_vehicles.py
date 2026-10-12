"""Provider-neutral models for user-owned saved vehicle snapshots."""

from dataclasses import dataclass
from datetime import datetime

from routevalue.application.models import (
    VehicleCatalogConfiguration,
    VehicleSpecificationUnavailableReason,
)
from routevalue.domain.identity import SavedVehicleId
from routevalue.domain.models import VehicleEnergySpecification


@dataclass(frozen=True, slots=True)
class SavedVehicleSnapshot:
    """Normalized vehicle specification ready for durable persistence."""

    configuration: VehicleCatalogConfiguration
    specification: VehicleEnergySpecification
    specification_retrieved_at: datetime

    def __post_init__(self) -> None:
        _require_timezone_aware(
            self.specification_retrieved_at,
            field_name="specification_retrieved_at",
        )


@dataclass(frozen=True, slots=True)
class SavedVehicle:
    """One durable RouteValue-owned vehicle snapshot."""

    id: SavedVehicleId
    configuration: VehicleCatalogConfiguration
    specification: VehicleEnergySpecification
    specification_retrieved_at: datetime
    saved_at: datetime

    def __post_init__(self) -> None:
        _require_timezone_aware(
            self.specification_retrieved_at,
            field_name="specification_retrieved_at",
        )
        _require_timezone_aware(
            self.saved_at,
            field_name="saved_at",
        )


@dataclass(frozen=True, slots=True)
class SavedVehicleCreationResult:
    """Outcome of attempting to save one catalog vehicle."""

    saved_vehicle: SavedVehicle | None
    unavailable_reason: VehicleSpecificationUnavailableReason | None

    def __post_init__(self) -> None:
        if (self.saved_vehicle is None) == (self.unavailable_reason is None):
            raise ValueError(
                "saved vehicle creation result requires exactly one of "
                "saved_vehicle or unavailable_reason"
            )


def _require_timezone_aware(
    value: datetime,
    *,
    field_name: str,
) -> None:
    """Require one timestamp to carry an explicit timezone."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
