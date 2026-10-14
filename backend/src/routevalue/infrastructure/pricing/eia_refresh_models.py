"""Explicit result contracts for controlled EIA gasoline price refreshes."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from routevalue.infrastructure.pricing.eia_geography import (
    EiaGasolineRegion,
)


class EiaRefreshStatus(StrEnum):
    """Outcome of a single regional EIA refresh attempt."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EiaRefreshFailureReason(StrEnum):
    """Classified failure of a controlled EIA refresh."""

    DOWNLOAD_FAILED = "download_failed"
    PARSE_FAILED = "parse_failed"
    NORMALIZATION_FAILED = "normalization_failed"
    SNAPSHOT_INVALID = "snapshot_invalid"
    PERSISTENCE_FAILED = "persistence_failed"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class EiaRefreshResult:
    """Immutable outcome of one regional refresh attempt.

    A successful result records the completed refresh timestamp.
    A failed result records an explicit reason and cannot claim
    a successful persistence timestamp.

    The timestamp represents refresh completion, not the EIA
    observation date used to evaluate gasoline-price freshness.
    """

    region: EiaGasolineRegion
    status: EiaRefreshStatus
    failure_reason: EiaRefreshFailureReason | None = None
    refreshed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.region, EiaGasolineRegion):
            raise TypeError("region must be an EiaGasolineRegion")

        if not isinstance(self.status, EiaRefreshStatus):
            raise TypeError("status must be an EiaRefreshStatus")

        if self.status is EiaRefreshStatus.SUCCEEDED:
            if self.failure_reason is not None:
                raise ValueError("successful refresh cannot have a failure reason")

            if self.refreshed_at is None:
                raise ValueError("successful refresh requires refreshed_at")

        else:
            if not isinstance(
                self.failure_reason,
                EiaRefreshFailureReason,
            ):
                raise ValueError("failed refresh requires a failure reason")

            if self.refreshed_at is not None:
                raise ValueError("failed refresh cannot claim refreshed_at")

        if self.refreshed_at is not None:
            if not isinstance(self.refreshed_at, datetime):
                raise TypeError("refreshed_at must be a datetime")

            if self.refreshed_at.tzinfo is None or self.refreshed_at.utcoffset() is None:
                raise ValueError("refreshed_at must be timezone-aware")

    @property
    def succeeded(self) -> bool:
        """Whether the snapshot was successfully persisted."""

        return self.status is EiaRefreshStatus.SUCCEEDED
