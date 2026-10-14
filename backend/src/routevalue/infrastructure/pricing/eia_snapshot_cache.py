"""Validated, process-local EIA gasoline pricing snapshot cache.

This module supplies immutable snapshots and atomic in-memory replacement.
It does not download workbooks, persist to a database, or determine whether
a gasoline quote is currently fresh for trip evaluation.
"""

from dataclasses import dataclass
from datetime import datetime
from threading import RLock

from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)

EIA_PROVIDER_NAME = "EIA"


@dataclass(frozen=True, slots=True)
class EiaPricingSnapshot:
    """One complete, validated regional EIA price snapshot."""

    region: EiaGasolineRegion
    quotes: tuple[GasolinePriceQuote, ...]
    refreshed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.region, EiaGasolineRegion):
            raise TypeError("region must be an EiaGasolineRegion")

        if self.region not in (
            EIA_CALIFORNIA_REGION,
            EIA_US_REGION,
        ):
            raise ValueError("unsupported EIA pricing region")

        if not isinstance(self.quotes, tuple):
            raise TypeError("quotes must be a tuple")

        if not isinstance(self.refreshed_at, datetime):
            raise TypeError("refreshed_at must be a datetime")

        if self.refreshed_at.tzinfo is None or self.refreshed_at.utcoffset() is None:
            raise ValueError("refreshed_at must be timezone-aware")

        if len(self.quotes) != len(GasolineGrade):
            raise ValueError("snapshot requires every gasoline grade")

        seen: set[GasolineGrade] = set()

        for quote in self.quotes:
            if not isinstance(quote, GasolinePriceQuote):
                raise TypeError("quotes must contain GasolinePriceQuote")

            if quote.fuel_grade in seen:
                raise ValueError("duplicate gasoline grade")

            seen.add(quote.fuel_grade)

            if quote.source is not GasolinePriceSource.REGIONAL_MARKET:
                raise ValueError("snapshot requires regional market quotes")

            if quote.observed_at is None:
                raise ValueError("snapshot quote requires observed_at")

            if quote.observed_at > self.refreshed_at:
                raise ValueError("observation cannot follow refresh time")

            metadata = quote.market_metadata

            if metadata is None:
                raise ValueError("snapshot quote requires market metadata")

            if metadata.provider != EIA_PROVIDER_NAME:
                raise ValueError("snapshot requires EIA provenance")

            if metadata.geography != self.region.geography:
                raise ValueError("snapshot geographic provenance mismatch")

        if seen != set(GasolineGrade):
            raise ValueError("snapshot has incomplete grade coverage")

        ordered = tuple(
            next(quote for quote in self.quotes if quote.fuel_grade is grade)
            for grade in GasolineGrade
        )

        object.__setattr__(self, "quotes", ordered)

    def quote_for_grade(
        self,
        grade: GasolineGrade,
    ) -> GasolinePriceQuote:
        """Return a validated quote for one grade."""

        if not isinstance(grade, GasolineGrade):
            raise TypeError("grade must be a GasolineGrade")

        return next(quote for quote in self.quotes if quote.fuel_grade is grade)


class EiaPricingSnapshotCache:
    """Thread-safe, process-local cache of validated EIA snapshots.

    Each region is replaced atomically. Failed validation leaves the
    previous regional snapshot intact.

    Refresh coordination across processes and durable persistence
    are intentionally outside this class.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._snapshots: dict[
            EiaGasolineRegion,
            EiaPricingSnapshot,
        ] = {}

    def get(
        self,
        region: EiaGasolineRegion,
    ) -> EiaPricingSnapshot | None:
        """Read one complete immutable regional snapshot."""

        if not isinstance(region, EiaGasolineRegion):
            raise TypeError("region must be an EiaGasolineRegion")

        with self._lock:
            return self._snapshots.get(region)

    def replace(
        self,
        snapshot: EiaPricingSnapshot,
    ) -> None:
        """Atomically replace a regional snapshot.

        Reject regressing refresh timestamps, regressing observation
        dates, and conflicting prices for the same observation date.

        A future explicit correction workflow may separately authorize
        revised EIA observations.
        """

        if not isinstance(snapshot, EiaPricingSnapshot):
            raise TypeError("snapshot must be an EiaPricingSnapshot")

        with self._lock:
            previous = self._snapshots.get(snapshot.region)

            if previous is not None:
                if snapshot.refreshed_at < previous.refreshed_at:
                    raise ValueError("refresh timestamp cannot regress")

                for grade in GasolineGrade:
                    old_quote = previous.quote_for_grade(grade)
                    new_quote = snapshot.quote_for_grade(grade)

                    if old_quote.observed_at is None or new_quote.observed_at is None:
                        raise ValueError("snapshot observations require timestamps")

                    if new_quote.observed_at < old_quote.observed_at:
                        raise ValueError("EIA observation date cannot regress")

                    if (
                        new_quote.observed_at == old_quote.observed_at
                        and new_quote.price_per_gallon != old_quote.price_per_gallon
                    ):
                        raise ValueError("conflicting EIA price for same observation date")

            self._snapshots[snapshot.region] = snapshot

    def regions(self) -> tuple[EiaGasolineRegion, ...]:
        """Return regions currently present in the cache."""

        with self._lock:
            return tuple(
                region
                for region in (
                    EIA_CALIFORNIA_REGION,
                    EIA_US_REGION,
                )
                if region in self._snapshots
            )
