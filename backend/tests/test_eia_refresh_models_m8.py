"""M8 tests for explicit EIA refresh results."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
)
from routevalue.infrastructure.pricing.eia_refresh_models import (
    EiaRefreshFailureReason,
    EiaRefreshResult,
    EiaRefreshStatus,
)

REFRESHED_AT = datetime(2026, 10, 13, 15, tzinfo=UTC)


def test_successful_refresh_result() -> None:
    result = EiaRefreshResult(
        region=EIA_CALIFORNIA_REGION,
        status=EiaRefreshStatus.SUCCEEDED,
        refreshed_at=REFRESHED_AT,
    )

    assert result.succeeded is True
    assert result.failure_reason is None
    assert result.refreshed_at == REFRESHED_AT


@pytest.mark.parametrize(
    "reason",
    list(EiaRefreshFailureReason),
)
def test_failed_refresh_has_explicit_reason(
    reason: EiaRefreshFailureReason,
) -> None:
    result = EiaRefreshResult(
        region=EIA_US_REGION,
        status=EiaRefreshStatus.FAILED,
        failure_reason=reason,
    )

    assert result.succeeded is False
    assert result.failure_reason is reason
    assert result.refreshed_at is None


def test_success_requires_refresh_timestamp() -> None:
    with pytest.raises(
        ValueError,
        match="requires refreshed_at",
    ):
        EiaRefreshResult(
            region=EIA_CALIFORNIA_REGION,
            status=EiaRefreshStatus.SUCCEEDED,
        )


def test_success_rejects_failure_reason() -> None:
    with pytest.raises(
        ValueError,
        match="cannot have a failure reason",
    ):
        EiaRefreshResult(
            region=EIA_CALIFORNIA_REGION,
            status=EiaRefreshStatus.SUCCEEDED,
            failure_reason=(EiaRefreshFailureReason.DOWNLOAD_FAILED),
            refreshed_at=REFRESHED_AT,
        )


def test_failure_requires_failure_reason() -> None:
    with pytest.raises(
        ValueError,
        match="requires a failure reason",
    ):
        EiaRefreshResult(
            region=EIA_CALIFORNIA_REGION,
            status=EiaRefreshStatus.FAILED,
        )


def test_failure_cannot_claim_successful_refresh() -> None:
    with pytest.raises(
        ValueError,
        match="cannot claim refreshed_at",
    ):
        EiaRefreshResult(
            region=EIA_US_REGION,
            status=EiaRefreshStatus.FAILED,
            failure_reason=(EiaRefreshFailureReason.PERSISTENCE_FAILED),
            refreshed_at=REFRESHED_AT,
        )


def test_naive_refresh_timestamp_is_rejected() -> None:
    naive_timestamp = REFRESHED_AT.replace(tzinfo=None)

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        EiaRefreshResult(
            region=EIA_CALIFORNIA_REGION,
            status=EiaRefreshStatus.SUCCEEDED,
            refreshed_at=naive_timestamp,
        )


def test_refresh_result_is_immutable() -> None:
    result = EiaRefreshResult(
        region=EIA_US_REGION,
        status=EiaRefreshStatus.SUCCEEDED,
        refreshed_at=REFRESHED_AT,
    )

    with pytest.raises(FrozenInstanceError):
        result.status = EiaRefreshStatus.FAILED  # type: ignore[misc]


def test_invalid_region_is_rejected() -> None:
    with pytest.raises(TypeError, match="EiaGasolineRegion"):
        EiaRefreshResult(
            region="California",  # type: ignore[arg-type]
            status=EiaRefreshStatus.SUCCEEDED,
            refreshed_at=REFRESHED_AT,
        )


def test_invalid_status_is_rejected() -> None:
    with pytest.raises(TypeError, match="EiaRefreshStatus"):
        EiaRefreshResult(
            region=EIA_US_REGION,
            status="succeeded",  # type: ignore[arg-type]
            refreshed_at=REFRESHED_AT,
        )
