"""Application service for user-owned saved vehicle snapshots."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

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
    SavedVehicleCreationResult,
    SavedVehicleSnapshot,
)
from routevalue.domain.identity import (
    SavedVehicleId,
    UserId,
)


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class UserSavedVehiclesService:
    """Manage durable vehicle snapshots for one RouteValue user."""

    repository: SavedVehicleRepository
    specification_provider: VehicleSpecificationProvider
    clock: Callable[[], datetime] = _utc_now

    def list_vehicles(
        self,
        user_id: UserId,
    ) -> tuple[SavedVehicle, ...]:
        """Return the authenticated user's saved vehicles."""

        return tuple(self.repository.list_vehicles(user_id))

    def get_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> SavedVehicle | None:
        """Return one vehicle only within the requesting user's ownership scope."""

        return self.repository.get_vehicle(
            user_id,
            vehicle_id,
        )

    def save_catalog_vehicle(
        self,
        user_id: UserId,
        configuration: VehicleCatalogConfiguration,
    ) -> SavedVehicleCreationResult:
        """Revalidate and persist one trusted normalized vehicle snapshot."""

        available_configurations = self.specification_provider.list_configurations(
            year=configuration.year,
            make=configuration.make,
            model=configuration.model,
        )

        canonical_configuration = next(
            (candidate for candidate in available_configurations if candidate == configuration),
            None,
        )

        if canonical_configuration is None:
            return SavedVehicleCreationResult(
                saved_vehicle=None,
                unavailable_reason=(VehicleSpecificationUnavailableReason.NOT_FOUND),
            )

        specification_result = self.specification_provider.get_specification(
            canonical_configuration
        )

        specification = specification_result.specification

        if specification is None:
            return SavedVehicleCreationResult(
                saved_vehicle=None,
                unavailable_reason=(specification_result.unavailable_reason),
            )

        snapshot = SavedVehicleSnapshot(
            configuration=canonical_configuration,
            # V2 mass is optional and entered separately by the owner. Catalog
            # efficiency remains authoritative, but must never supply mass.
            specification=replace(specification, vehicle_mass=None),
            specification_retrieved_at=self.clock(),
        )

        saved_vehicle = self.repository.create_vehicle(
            user_id,
            snapshot,
        )

        return SavedVehicleCreationResult(
            saved_vehicle=saved_vehicle,
            unavailable_reason=None,
        )

    def delete_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> bool:
        """Delete one vehicle only inside the requesting user's ownership scope."""

        return self.repository.delete_vehicle(
            user_id,
            vehicle_id,
        )
