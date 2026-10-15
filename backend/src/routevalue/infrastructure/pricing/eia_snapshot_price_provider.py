"""Read-only EIA gasoline price provider backed by durable snapshots."""

from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from routevalue.application.gasoline_price_failures import (
    GasolinePriceProviderError,
    GasolinePriceProviderFailureReason,
    GasolinePriceUnavailableError,
    GasolinePriceUnavailableReason,
)
from routevalue.application.gasoline_price_ports import (
    GasolinePriceLookupRequest,
)
from routevalue.domain.models import GasolinePriceQuote
from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    EiaPricingPersistenceError,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_snapshot_cache import (
    EiaPricingSnapshot,
)


class EiaSnapshotReader(Protocol):
    """Read complete EIA snapshots without modifying stored data."""

    def get_snapshot(
        self,
        region: EiaGasolineRegion,
    ) -> EiaPricingSnapshot | None: ...


_SUPPORTED_REGIONS = (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
)


class PostgresEiaGasolinePriceProvider:
    """Adapt persisted EIA snapshots to the gasoline pricing port.

    Price freshness and geographic fallback remain the responsibility
    of the application pricing-selection layer.

    This adapter performs no HTTP requests, snapshot writes, or
    in-memory caching.
    """

    def __init__(
        self,
        *,
        repository: EiaSnapshotReader,
    ) -> None:
        self._repository = repository

    def get_price(
        self,
        request: GasolinePriceLookupRequest,
    ) -> GasolinePriceQuote | None:
        """Return the matching grade from a complete stored snapshot."""

        if not isinstance(request, GasolinePriceLookupRequest):
            raise TypeError("request must be a GasolinePriceLookupRequest")

        region = next(
            (
                candidate
                for candidate in _SUPPORTED_REGIONS
                if candidate.geography == request.geography
            ),
            None,
        )

        if region is None:
            raise GasolinePriceUnavailableError(
                GasolinePriceUnavailableReason.UNSUPPORTED_GEOGRAPHY
            )

        try:
            snapshot = self._repository.get_snapshot(region)
        except EiaPricingPersistenceError as exc:
            raise GasolinePriceProviderError(
                GasolinePriceProviderFailureReason.INVALID_RESPONSE
            ) from exc
        except SQLAlchemyError as exc:
            raise GasolinePriceProviderError(
                GasolinePriceProviderFailureReason.UPSTREAM_UNAVAILABLE
            ) from exc

        if snapshot is None:
            return None

        if not isinstance(snapshot, EiaPricingSnapshot):
            raise GasolinePriceProviderError(GasolinePriceProviderFailureReason.INVALID_RESPONSE)

        if snapshot.region != region:
            raise GasolinePriceProviderError(GasolinePriceProviderFailureReason.INVALID_RESPONSE)

        return snapshot.quote_for_grade(request.fuel_grade)
