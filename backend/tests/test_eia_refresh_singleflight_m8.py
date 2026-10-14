"""Concurrency tests for single-process EIA refresh admission."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

import pytest

from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_refresh_models import (
    EiaRefreshResult,
    EiaRefreshStatus,
)
from routevalue.infrastructure.pricing.eia_refresh_singleflight import (
    EiaRefreshAlreadyRunningError,
    EiaSingleFlightRefreshRunner,
)

REFRESHED_AT = datetime(2026, 10, 13, 18, tzinfo=UTC)


class BlockingCoordinator:
    """Test double whose refresh can be held until released."""

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.calls = 0
        self.error: Exception | None = None

    def refresh(
        self,
        region: EiaGasolineRegion,
    ) -> EiaRefreshResult:
        self.calls += 1
        self.started.set()

        if not self.release.wait(timeout=5):
            raise TimeoutError("test refresh was not released")

        if self.error is not None:
            raise self.error

        return EiaRefreshResult(
            region=region,
            status=EiaRefreshStatus.SUCCEEDED,
            refreshed_at=REFRESHED_AT,
        )


def test_overlapping_same_region_is_rejected() -> None:
    coordinator = BlockingCoordinator()
    runner = EiaSingleFlightRefreshRunner(coordinator=coordinator)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            runner.refresh,
            EIA_CALIFORNIA_REGION,
        )

        try:
            assert coordinator.started.wait(timeout=5)

            with pytest.raises(
                EiaRefreshAlreadyRunningError,
                match="already running",
            ):
                runner.refresh(EIA_CALIFORNIA_REGION)
        finally:
            coordinator.release.set()

        result = future.result(timeout=5)

    assert result.succeeded
    assert coordinator.calls == 1


def test_overlapping_different_regions_are_rejected() -> None:
    """One runner permits only one active refresh globally."""

    coordinator = BlockingCoordinator()
    runner = EiaSingleFlightRefreshRunner(coordinator=coordinator)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            runner.refresh,
            EIA_CALIFORNIA_REGION,
        )

        try:
            assert coordinator.started.wait(timeout=5)

            with pytest.raises(EiaRefreshAlreadyRunningError):
                runner.refresh(EIA_US_REGION)
        finally:
            coordinator.release.set()

        assert future.result(timeout=5).succeeded

    assert coordinator.calls == 1


def test_sequential_refreshes_are_allowed() -> None:
    coordinator = BlockingCoordinator()
    coordinator.release.set()

    runner = EiaSingleFlightRefreshRunner(coordinator=coordinator)

    first = runner.refresh(EIA_CALIFORNIA_REGION)
    second = runner.refresh(EIA_US_REGION)

    assert first.succeeded
    assert second.succeeded
    assert coordinator.calls == 2


def test_lock_releases_after_underlying_failure() -> None:
    coordinator = BlockingCoordinator()
    coordinator.release.set()
    coordinator.error = RuntimeError("simulated failure")

    runner = EiaSingleFlightRefreshRunner(coordinator=coordinator)

    with pytest.raises(RuntimeError, match="simulated failure"):
        runner.refresh(EIA_US_REGION)

    coordinator.error = None

    result = runner.refresh(EIA_US_REGION)

    assert result.succeeded
    assert coordinator.calls == 2
