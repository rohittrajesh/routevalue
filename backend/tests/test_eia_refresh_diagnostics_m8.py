"""M8 regression tests for EIA refresh operational diagnostics."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_refresh_diagnostics import (
    EiaObservedRefreshRunner,
)
from routevalue.infrastructure.pricing.eia_refresh_models import (
    EiaRefreshFailureReason,
    EiaRefreshResult,
    EiaRefreshStatus,
)
from routevalue.infrastructure.pricing.eia_refresh_singleflight import (
    EiaRefreshAlreadyRunningError,
)

REFRESHED_AT = datetime(2026, 10, 13, 18, tzinfo=UTC)


class FakeRefreshOperation:
    """Deterministic refresh operation for diagnostics testing."""

    def __init__(
        self,
        *,
        result: EiaRefreshResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def refresh(
        self,
        region: EiaGasolineRegion,
    ) -> EiaRefreshResult:
        self.calls += 1

        if self.error is not None:
            raise self.error

        if self.result is None:
            raise RuntimeError("test operation has no result")

        return self.result


def make_clock() -> Callable[[], float]:
    values = iter((10.0, 10.25))
    return lambda: next(values)


def test_success_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = EiaRefreshResult(
        region=EIA_CALIFORNIA_REGION,
        status=EiaRefreshStatus.SUCCEEDED,
        refreshed_at=REFRESHED_AT,
    )

    operation = FakeRefreshOperation(result=result)
    runner = EiaObservedRefreshRunner(
        coordinator=operation,
        clock=make_clock(),
    )

    with caplog.at_level(logging.INFO):
        actual = runner.refresh(EIA_CALIFORNIA_REGION)

    assert actual is result
    assert operation.calls == 1
    assert "eia_refresh_started" in caplog.text
    assert "region_id=SCA" in caplog.text
    assert "status=succeeded" in caplog.text
    assert "duration_seconds=0.250000" in caplog.text


def test_failed_result_is_logged_with_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = EiaRefreshResult(
        region=EIA_US_REGION,
        status=EiaRefreshStatus.FAILED,
        failure_reason=EiaRefreshFailureReason.DOWNLOAD_FAILED,
    )

    operation = FakeRefreshOperation(result=result)
    runner = EiaObservedRefreshRunner(
        coordinator=operation,
        clock=make_clock(),
    )

    with caplog.at_level(logging.INFO):
        actual = runner.refresh(EIA_US_REGION)

    assert actual is result
    assert actual.succeeded is False
    assert "region_id=NUS" in caplog.text
    assert "status=failed" in caplog.text
    assert "failure_reason=download_failed" in caplog.text


def test_unexpected_exception_is_logged_and_propagated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    operation = FakeRefreshOperation(error=RuntimeError("secret-diagnostic-marker"))

    runner = EiaObservedRefreshRunner(
        coordinator=operation,
        clock=make_clock(),
    )

    with (
        caplog.at_level(logging.ERROR),
        pytest.raises(
            RuntimeError,
            match="secret-diagnostic-marker",
        ),
    ):
        runner.refresh(EIA_CALIFORNIA_REGION)

    assert "eia_refresh_exception" in caplog.text
    assert "exception_type=RuntimeError" in caplog.text
    assert "secret-diagnostic-marker" not in caplog.text


def test_singleflight_rejection_is_observed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class RejectingOperation:
        def refresh(
            self,
            region: EiaGasolineRegion,
        ) -> EiaRefreshResult:
            raise EiaRefreshAlreadyRunningError("an EIA pricing refresh is already running")

    runner = EiaObservedRefreshRunner(
        coordinator=RejectingOperation(),
        clock=make_clock(),
    )

    with caplog.at_level(logging.ERROR), pytest.raises(EiaRefreshAlreadyRunningError):
        runner.refresh(EIA_US_REGION)

    assert "region_id=NUS" in caplog.text
    assert "exception_type=EiaRefreshAlreadyRunningError" in caplog.text
