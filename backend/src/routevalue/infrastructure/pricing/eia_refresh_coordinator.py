"""Controlled orchestration of EIA gasoline pricing refreshes.

Refreshes are explicit operations, never initiated by trip evaluation.
HTTP transport and persistence are injected through narrow interfaces.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

import httpx
from sqlalchemy.exc import SQLAlchemyError

from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    EiaPricingPersistenceError,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_quote_normalization import (
    normalize_eia_observations,
)
from routevalue.infrastructure.pricing.eia_refresh_models import (
    EiaRefreshFailureReason,
    EiaRefreshResult,
    EiaRefreshStatus,
)
from routevalue.infrastructure.pricing.eia_retrieval_models import (
    EiaRetrievalError,
)
from routevalue.infrastructure.pricing.eia_snapshot_cache import (
    EiaPricingSnapshot,
)
from routevalue.infrastructure.pricing.eia_xls_parser import (
    parse_eia_xls_workbook,
)

WorkbookFetcher = Callable[[EiaGasolineRegion], bytes]
Clock = Callable[[], datetime]

_SUPPORTED_REGIONS = (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
)


class EiaSnapshotWriter(Protocol):
    """Persistence boundary for complete EIA snapshots."""

    def save_snapshot(
        self,
        snapshot: EiaPricingSnapshot,
    ) -> None:
        """Atomically persist a validated snapshot."""


class EiaRefreshCoordinator:
    """Refresh one supported EIA region through a validated pipeline.

    Expected transport, data, conflict, and database failures are
    classified explicitly. Unexpected programming errors propagate.

    A failure before persistence cannot modify stored pricing.
    Database failures rely on repository transaction rollback.
    """

    def __init__(
        self,
        *,
        fetch_workbook: WorkbookFetcher,
        repository: EiaSnapshotWriter,
        clock: Clock | None = None,
    ) -> None:
        self._fetch_workbook = fetch_workbook
        self._repository = repository
        self._clock = clock or _utc_now

    def refresh(
        self,
        region: EiaGasolineRegion,
    ) -> EiaRefreshResult:
        """Attempt one complete regional refresh."""

        if not isinstance(region, EiaGasolineRegion):
            raise TypeError("region must be an EiaGasolineRegion")

        if region not in _SUPPORTED_REGIONS:
            raise ValueError("unsupported EIA pricing region")

        try:
            workbook_bytes = self._fetch_workbook(region)
        except (EiaRetrievalError, httpx.HTTPError, OSError):
            return _failure(
                region,
                EiaRefreshFailureReason.DOWNLOAD_FAILED,
            )

        if not isinstance(workbook_bytes, bytes):
            raise TypeError("workbook fetcher must return bytes")

        try:
            observations = parse_eia_xls_workbook(
                workbook_bytes=workbook_bytes,
                region=region,
            )
        except (ValueError, TypeError):
            return _failure(
                region,
                EiaRefreshFailureReason.PARSE_FAILED,
            )

        try:
            quotes = normalize_eia_observations(
                observations=observations,
                region=region,
            )
        except (ValueError, TypeError):
            return _failure(
                region,
                EiaRefreshFailureReason.NORMALIZATION_FAILED,
            )

        refreshed_at = self._clock()

        if not isinstance(refreshed_at, datetime):
            raise TypeError("clock must return a datetime")

        if refreshed_at.tzinfo is None or refreshed_at.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")

        try:
            snapshot = EiaPricingSnapshot(
                region=region,
                quotes=quotes,
                refreshed_at=refreshed_at,
            )
        except (ValueError, TypeError):
            return _failure(
                region,
                EiaRefreshFailureReason.SNAPSHOT_INVALID,
            )

        try:
            self._repository.save_snapshot(snapshot)
        except ValueError:
            return _failure(
                region,
                EiaRefreshFailureReason.CONFLICT,
            )
        except (SQLAlchemyError, EiaPricingPersistenceError):
            return _failure(
                region,
                EiaRefreshFailureReason.PERSISTENCE_FAILED,
            )

        return EiaRefreshResult(
            region=region,
            status=EiaRefreshStatus.SUCCEEDED,
            refreshed_at=refreshed_at,
        )


def _utc_now() -> datetime:
    """Return the current UTC time."""

    return datetime.now(UTC)


def _failure(
    region: EiaGasolineRegion,
    reason: EiaRefreshFailureReason,
) -> EiaRefreshResult:
    """Construct an explicit failed refresh result."""

    return EiaRefreshResult(
        region=region,
        status=EiaRefreshStatus.FAILED,
        failure_reason=reason,
    )
