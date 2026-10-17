"""Application boundary for updating mass on user-owned vehicles."""

from dataclasses import dataclass
from typing import Protocol

from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.vehicle_mass import VehicleMass


class VehicleMassWriteRepository(Protocol):
    """Port for updating only a caller-owned saved vehicle."""

    def update_vehicle_mass(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
        mass: VehicleMass | None,
    ) -> SavedVehicle | None:
        """Return the updated vehicle, or None if it is not owned."""
        ...


@dataclass(frozen=True, slots=True)
class UserVehicleMassService:
    """Persist validated mass without modifying trusted efficiency data."""

    repository: VehicleMassWriteRepository

    def update_mass(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
        mass: VehicleMass | None,
    ) -> SavedVehicle | None:
        """Update mass using the authenticated ownership boundary."""

        return self.repository.update_vehicle_mass(
            user_id,
            vehicle_id,
            mass,
        )
