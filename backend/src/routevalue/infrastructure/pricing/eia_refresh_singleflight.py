"""Single-process admission control for EIA pricing refreshes.

This guard prevents overlapping refreshes through the same runner
instance. It does not provide cross-process or distributed locking.
"""

from threading import Lock
from typing import Protocol

from routevalue.infrastructure.pricing.eia_geography import (
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_refresh_models import (
    EiaRefreshResult,
)


class EiaRefreshAlreadyRunningError(RuntimeError):
    """A refresh is already active through this runner."""


class EiaRefreshOperation(Protocol):
    """An operation that refreshes one EIA gasoline region."""

    def refresh(
        self,
        region: EiaGasolineRegion,
    ) -> EiaRefreshResult:
        """Execute one complete refresh."""


class EiaSingleFlightRefreshRunner:
    """Reject overlapping refreshes within one runner instance.

    A non-blocking lock prevents a second caller from starting
    another refresh while the first caller is still executing.

    The lock is released even when the underlying operation raises.
    """

    def __init__(
        self,
        *,
        coordinator: EiaRefreshOperation,
    ) -> None:
        self._coordinator = coordinator
        self._lock = Lock()

    def refresh(
        self,
        region: EiaGasolineRegion,
    ) -> EiaRefreshResult:
        """Execute one refresh or explicitly reject overlap."""

        if not self._lock.acquire(blocking=False):
            raise EiaRefreshAlreadyRunningError("an EIA pricing refresh is already running")

        try:
            return self._coordinator.refresh(region)
        finally:
            self._lock.release()
