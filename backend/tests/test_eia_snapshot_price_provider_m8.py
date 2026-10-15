"""Tests for read-only EIA snapshot gasoline price adaptation."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import OperationalError

from routevalue.application.gasoline_price_failures import (
    GasolinePriceProviderError,
    GasolinePriceProviderFailureReason,
    GasolinePriceUnavailableError,
    GasolinePriceUnavailableReason,
)
from routevalue.application.gasoline_price_ports import (
    GasolinePriceLookupRequest,
    GasolinePriceProvider,
)
from routevalue.domain.gasoline_price_metadata import (
    GasolinePriceGeographicScope,
    GasolinePriceGeography,
)
from routevalue.domain.models import GasolineGrade, GasolinePriceSource
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
from routevalue.infrastructure.pricing.eia_snapshot_cache import (
    EiaPricingSnapshot,
)
from routevalue.infrastructure.pricing.eia_snapshot_price_provider import (
    PostgresEiaGasolinePriceProvider,
)
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaGasolineObservation,
)

REFRESHED_AT = datetime(2026, 10, 13, 15, tzinfo=UTC)


def make_snapshot(
    region: EiaGasolineRegion,
) -> EiaPricingSnapshot:
    observations = tuple(
        EiaGasolineObservation(
            series_id=region.series_for_grade(grade),
            fuel_grade=grade,
            observed_on=date(2026, 10, 12),
            price_per_gallon=Decimal("5.123"),
        )
        for grade in GasolineGrade
    )

    return EiaPricingSnapshot(
        region=region,
        quotes=normalize_eia_observations(
            observations=observations,
            region=region,
        ),
        refreshed_at=REFRESHED_AT,
    )


class FakeSnapshotRepository:
    def __init__(
        self,
        snapshots: dict[EiaGasolineRegion, EiaPricingSnapshot] | None = None,
    ) -> None:
        self.snapshots = snapshots or {}
        self.calls: list[EiaGasolineRegion] = []

    def get_snapshot(
        self,
        region: EiaGasolineRegion,
    ) -> EiaPricingSnapshot | None:
        self.calls.append(region)
        return self.snapshots.get(region)


def make_request(
    region: EiaGasolineRegion,
    grade: GasolineGrade = GasolineGrade.REGULAR,
) -> GasolinePriceLookupRequest:
    return GasolinePriceLookupRequest(
        fuel_grade=grade,
        geography=region.geography,
    )


def test_provider_satisfies_pricing_protocol() -> None:
    repository = FakeSnapshotRepository()

    provider: GasolinePriceProvider = PostgresEiaGasolinePriceProvider(repository=repository)

    assert provider.get_price(make_request(EIA_US_REGION)) is None


@pytest.mark.parametrize("grade", list(GasolineGrade))
def test_returns_exact_requested_grade(
    grade: GasolineGrade,
) -> None:
    snapshot = make_snapshot(EIA_CALIFORNIA_REGION)
    repository = FakeSnapshotRepository({EIA_CALIFORNIA_REGION: snapshot})

    provider = PostgresEiaGasolinePriceProvider(repository=repository)

    quote = provider.get_price(make_request(EIA_CALIFORNIA_REGION, grade))

    assert quote is not None
    assert quote.fuel_grade is grade
    assert quote.price_per_gallon == Decimal("5.123")
    assert quote.source is GasolinePriceSource.REGIONAL_MARKET
    assert quote.market_metadata is not None
    assert quote.market_metadata.geography == EIA_CALIFORNIA_REGION.geography
    assert repository.calls == [EIA_CALIFORNIA_REGION]


def test_national_lookup_does_not_read_california() -> None:
    repository = FakeSnapshotRepository(
        {
            EIA_CALIFORNIA_REGION: make_snapshot(EIA_CALIFORNIA_REGION),
            EIA_US_REGION: make_snapshot(EIA_US_REGION),
        }
    )

    provider = PostgresEiaGasolinePriceProvider(repository=repository)

    quote = provider.get_price(make_request(EIA_US_REGION))

    assert quote is not None
    assert quote.market_metadata is not None
    assert quote.market_metadata.geography == EIA_US_REGION.geography
    assert repository.calls == [EIA_US_REGION]


def test_missing_snapshot_returns_none() -> None:
    repository = FakeSnapshotRepository()
    provider = PostgresEiaGasolinePriceProvider(repository=repository)

    assert provider.get_price(make_request(EIA_CALIFORNIA_REGION)) is None
    assert repository.calls == [EIA_CALIFORNIA_REGION]


def test_unsupported_geography_rejected_before_database_access() -> None:
    repository = FakeSnapshotRepository()
    provider = PostgresEiaGasolinePriceProvider(repository=repository)

    unsupported = GasolinePriceGeography(
        scope=GasolinePriceGeographicScope.STATE,
        region_id="SNY",
        display_name="New York",
    )

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        provider.get_price(
            GasolinePriceLookupRequest(
                fuel_grade=GasolineGrade.REGULAR,
                geography=unsupported,
            )
        )

    assert exc.value.reason is GasolinePriceUnavailableReason.UNSUPPORTED_GEOGRAPHY
    assert repository.calls == []


def test_corrupt_stored_snapshot_is_not_treated_as_missing() -> None:
    class CorruptRepository:
        def get_snapshot(
            self,
            region: EiaGasolineRegion,
        ) -> EiaPricingSnapshot | None:
            raise EiaPricingPersistenceError("invalid stored provenance")

    provider = PostgresEiaGasolinePriceProvider(repository=CorruptRepository())

    with pytest.raises(GasolinePriceProviderError) as exc:
        provider.get_price(make_request(EIA_US_REGION))

    assert exc.value.reason is GasolinePriceProviderFailureReason.INVALID_RESPONSE


def test_database_failure_is_not_treated_as_missing() -> None:
    class FailingRepository:
        def get_snapshot(
            self,
            region: EiaGasolineRegion,
        ) -> EiaPricingSnapshot | None:
            raise OperationalError(
                "SELECT snapshot",
                {},
                RuntimeError("database unavailable"),
            )

    provider = PostgresEiaGasolinePriceProvider(repository=FailingRepository())

    with pytest.raises(GasolinePriceProviderError) as exc:
        provider.get_price(make_request(EIA_US_REGION))

    assert exc.value.reason is GasolinePriceProviderFailureReason.UPSTREAM_UNAVAILABLE
