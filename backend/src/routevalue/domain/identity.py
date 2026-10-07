"""Provider-neutral user identity for RouteValue."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserId:
    """Permanent internal RouteValue user identifier."""

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise TypeError("UserId must contain a UUID")
