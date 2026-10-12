"""Stable RouteValue-owned identifiers."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserId:
    """Permanent internal RouteValue user identifier."""

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise TypeError("UserId must contain a UUID")


@dataclass(frozen=True, slots=True)
class SavedVehicleId:
    """Permanent identifier for one user-owned saved vehicle."""

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise TypeError("SavedVehicleId must contain a UUID")
