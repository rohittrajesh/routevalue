"""Structured operational diagnostics for EIA gasoline refreshes.

Logs refresh outcomes without exposing credentials, workbook contents,
or raw exception messages.

The wrapped operation remains responsible for refresh execution and
persistence correctness.
"""

import logging
from collections.abc import Callable
from time import perf_counter

from routevalue.infrastructure.pricing.eia_geography import (
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_refresh_models import (
    EiaRefreshResult,
)
from routevalue.infrastructure.pricing.eia_refresh_singleflight import (
    EiaRefreshOperation,
)

Clock = Callable[[], float]

_LOGGER = logging.getLogger(__name__)


class EiaObservedRefreshRunner:
    """Record structured diagnostics for one refresh operation.

    This wrapper does not initiate background work, retry failures,
    or manage cross-process concurrency.
    """

    def __init__(
        self,
        *,
        coordinator: EiaRefreshOperation,
        clock: Clock | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._clock = clock or perf_counter

    def refresh(
        self,
        region: EiaGasolineRegion,
    ) -> EiaRefreshResult:
        """Run a refresh and log its outcome."""

        region_id = (
            region.geography.region_id if isinstance(region, EiaGasolineRegion) else "invalid"
        )

        started = self._clock()

        _LOGGER.info(
            "eia_refresh_started region_id=%s",
            region_id,
        )

        try:
            result = self._coordinator.refresh(region)
        except Exception as exc:
            elapsed = max(0.0, self._clock() - started)

            _LOGGER.error(
                "eia_refresh_exception region_id=%s exception_type=%s duration_seconds=%.6f",
                region_id,
                type(exc).__name__,
                elapsed,
            )

            raise

        elapsed = max(0.0, self._clock() - started)

        if result.succeeded:
            _LOGGER.info(
                "eia_refresh_finished region_id=%s status=succeeded duration_seconds=%.6f",
                region_id,
                elapsed,
            )
        else:
            reason = result.failure_reason

            _LOGGER.warning(
                "eia_refresh_finished "
                "region_id=%s "
                "status=failed "
                "failure_reason=%s "
                "duration_seconds=%.6f",
                region_id,
                reason.value if reason is not None else "unknown",
                elapsed,
            )

        return result
