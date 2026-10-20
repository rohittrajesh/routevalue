"""Fail-closed, process-local budget protection for public elevation access.

This limiter is suitable for a single local development process only.
For multi-worker or multi-instance deployments, use a shared distributed
limiter before permitting live public API traffic.
"""

import os
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from threading import Lock
from time import monotonic, sleep
from typing import Protocol

from routevalue.application.terrain import ElevationSample
from routevalue.application.terrain_batching import (
    MAX_ELEVATION_BATCH_SIZE,
    plan_elevation_batches,
)
from routevalue.application.terrain_ports import (
    ElevationProvider,
    ElevationProviderError,
    ElevationProviderQuotaError,
)
from routevalue.application.terrain_sampling import TerrainSampleLocation

TERRAIN_LIVE_ENABLED_ENV = "ROUTEVALUE_TERRAIN_LIVE_ENABLED"
_SECONDS_PER_DAY = 86_400.0


class ElevationAccessDisabledError(ElevationProviderError):
    """Explicit opt-in to live elevation acquisition is missing."""


class ElevationTripBudgetExceededError(ElevationProviderQuotaError):
    """One trip would exceed its elevation HTTP-call allowance."""


class ElevationDailyBudgetExceededError(ElevationProviderQuotaError):
    """Shared in-process rolling 24-hour request budget has been consumed."""


@dataclass(frozen=True, slots=True)
class PublicElevationPolicy:
    """Conservative limits below Open Topo Data's published public limits."""

    max_requests_per_trip: int = 5
    max_requests_per_24_hours: int = 900
    minimum_interval_seconds: float = 1.1

    def __post_init__(self) -> None:
        if isinstance(self.max_requests_per_trip, bool) or not isinstance(
            self.max_requests_per_trip, int
        ):
            raise TypeError("max_requests_per_trip must be an integer")
        if not 1 <= self.max_requests_per_trip <= 6:
            raise ValueError("max_requests_per_trip must be between 1 and 6")
        if isinstance(self.max_requests_per_24_hours, bool) or not isinstance(
            self.max_requests_per_24_hours, int
        ):
            raise TypeError("max_requests_per_24_hours must be an integer")
        if not 1 <= self.max_requests_per_24_hours <= 900:
            raise ValueError("max_requests_per_24_hours must be between 1 and 900")
        if isinstance(self.minimum_interval_seconds, bool) or not isinstance(
            self.minimum_interval_seconds, (float, int)
        ):
            raise TypeError("minimum_interval_seconds must be a number")
        if not isfinite(self.minimum_interval_seconds) or self.minimum_interval_seconds < 1.1:
            raise ValueError("minimum_interval_seconds must be at least 1.1")


def terrain_live_enabled(
    environment: Mapping[str, str] | None = None,
) -> bool:
    """Require explicit '1'; reject misspellings rather than enabling by accident."""

    values = os.environ if environment is None else environment
    setting = values.get(TERRAIN_LIVE_ENABLED_ENV, "0")
    if setting not in ("0", "1"):
        raise ValueError(f"{TERRAIN_LIVE_ENABLED_ENV} must be exactly '0' or '1'")
    return setting == "1"


class PublicElevationCallGate:
    """Serialize and count each attempted HTTP call in one Python process.

    Call reserve immediately before invoking the external provider.
    Failed upstream calls still consume a reservation; no retries occur here.
    A single gate must be shared by all trips in a development process.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        policy: PublicElevationPolicy | None = None,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a boolean")
        self.enabled = enabled
        self.policy = policy if policy is not None else PublicElevationPolicy()
        self._clock = clock
        self._sleeper = sleeper
        self._lock = Lock()
        self._reservations: deque[float] = deque()
        self._last_reservation: float | None = None

    def reserve(self) -> None:
        """Atomically enforce the rolling budget and inter-request spacing."""

        if not self.enabled:
            raise ElevationAccessDisabledError("live elevation access is disabled")

        with self._lock:
            now = self._clock()
            if not isfinite(now):
                raise ValueError("monotonic clock must be finite")
            if self._last_reservation is not None and now < self._last_reservation:
                raise ValueError("monotonic clock cannot move backwards")

            while self._reservations and now - self._reservations[0] >= _SECONDS_PER_DAY:
                self._reservations.popleft()
            if len(self._reservations) >= self.policy.max_requests_per_24_hours:
                raise ElevationDailyBudgetExceededError("24-hour elevation budget exhausted")

            if self._last_reservation is not None:
                delay = self._last_reservation + self.policy.minimum_interval_seconds - now
                if delay > 0:
                    self._sleeper(delay)
                    now = self._clock()
                    if not isfinite(now) or now < (
                        self._last_reservation + self.policy.minimum_interval_seconds - 1e-9
                    ):
                        raise RuntimeError("clock did not advance after rate-limit wait")

            self._reservations.append(now)
            self._last_reservation = now

    def new_trip(self, delegate: ElevationProvider) -> "GuardedElevationTripProvider":
        """Create a per-trip budget sharing this process-wide request limiter."""

        return GuardedElevationTripProvider(delegate=delegate, gate=self)


class GuardedElevationTripProvider:
    """Apply one trip's bounded allowance before invoking the real provider."""

    def __init__(self, *, delegate: ElevationProvider, gate: "ElevationCallGate") -> None:
        self._delegate = delegate
        self._gate = gate
        self._calls = 0
        self._lock = Lock()

    @property
    def request_count(self) -> int:
        with self._lock:
            return self._calls

    def get_elevations(
        self,
        locations: Sequence[TerrainSampleLocation],
    ) -> tuple[ElevationSample, ...]:
        """Execute one validated batch; never automatically retry it."""

        plan = plan_elevation_batches(
            locations,
            max_batch_size=MAX_ELEVATION_BATCH_SIZE,
            max_samples=MAX_ELEVATION_BATCH_SIZE,
        )
        if not plan.batches:
            return ()
        if len(plan.batches) != 1:
            raise ValueError("a single elevation call cannot contain multiple batches")

        with self._lock:
            if self._calls >= self._gate.policy.max_requests_per_trip:
                raise ElevationTripBudgetExceededError("trip elevation budget exhausted")
            self._gate.reserve()
            self._calls += 1

        return self._delegate.get_elevations(plan.batches[0])


class ElevationCallGate(Protocol):
    """Infrastructure gate shared by process-local and durable compositions."""

    @property
    def policy(self) -> PublicElevationPolicy: ...

    def reserve(self) -> None: ...

    def new_trip(self, delegate: ElevationProvider) -> GuardedElevationTripProvider: ...
