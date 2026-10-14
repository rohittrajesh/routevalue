"""M8 validated EIA pricing snapshot and atomic cache tests."""

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

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
from routevalue.infrastructure.pricing.eia_quote_normalization import (
    normalize_eia_observations,
)
from routevalue.infrastructure.pricing.eia_snapshot_cache import (
    EiaPricingSnapshot,
    EiaPricingSnapshotCache,
)
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaGasolineObservation,
)

REFRESHED_AT = datetime(2026, 10, 13, 15, tzinfo=UTC)
OBSERVED_ON = date(2026, 10, 5)


def make_quotes(
    region: EiaGasolineRegion = EIA_CALIFORNIA_REGION,
    *,
    observed_on: date = OBSERVED_ON,
) -> tuple[GasolinePriceQuote, ...]:
    observations = tuple(
        EiaGasolineObservation(
            series_id=region.series_for_grade(grade),
            fuel_grade=grade,
            observed_on=observed_on,
            price_per_gallon=Decimal("5.123"),
        )
        for grade in GasolineGrade
    )

    return normalize_eia_observations(
        observations=observations,
        region=region,
    )


def make_snapshot(
    region: EiaGasolineRegion = EIA_CALIFORNIA_REGION,
    *,
    observed_on: date = OBSERVED_ON,
    refreshed_at: datetime = REFRESHED_AT,
) -> EiaPricingSnapshot:
    return EiaPricingSnapshot(
        region=region,
        quotes=make_quotes(region, observed_on=observed_on),
        refreshed_at=refreshed_at,
    )


def test_valid_snapshot_preserves_region_and_refresh() -> None:
    snapshot = make_snapshot()

    assert snapshot.region == EIA_CALIFORNIA_REGION
    assert snapshot.refreshed_at == REFRESHED_AT
    assert len(snapshot.quotes) == 3


def test_quotes_are_ordered_by_gasoline_grade() -> None:
    quotes = make_quotes()

    snapshot = EiaPricingSnapshot(
        region=EIA_CALIFORNIA_REGION,
        quotes=tuple(reversed(quotes)),
        refreshed_at=REFRESHED_AT,
    )

    assert [quote.fuel_grade for quote in snapshot.quotes] == list(GasolineGrade)


def test_quote_lookup_returns_correct_grade() -> None:
    snapshot = make_snapshot()

    assert snapshot.quote_for_grade(GasolineGrade.PREMIUM).fuel_grade is GasolineGrade.PREMIUM


def test_snapshot_is_frozen() -> None:
    snapshot = make_snapshot()

    with pytest.raises(FrozenInstanceError):
        snapshot.refreshed_at = REFRESHED_AT  # type: ignore[misc]


def test_naive_refresh_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EiaPricingSnapshot(
            region=EIA_CALIFORNIA_REGION,
            quotes=make_quotes(),
            refreshed_at=REFRESHED_AT.replace(tzinfo=None),
        )


def test_missing_grade_is_rejected() -> None:
    with pytest.raises(ValueError, match="every gasoline grade"):
        EiaPricingSnapshot(
            region=EIA_CALIFORNIA_REGION,
            quotes=make_quotes()[:2],
            refreshed_at=REFRESHED_AT,
        )


def test_duplicate_grade_is_rejected() -> None:
    quotes = make_quotes()

    with pytest.raises(ValueError, match="duplicate gasoline grade"):
        EiaPricingSnapshot(
            region=EIA_CALIFORNIA_REGION,
            quotes=(quotes[0], quotes[0], quotes[2]),
            refreshed_at=REFRESHED_AT,
        )


def test_wrong_geographic_provenance_is_rejected() -> None:
    with pytest.raises(ValueError, match="geographic provenance"):
        EiaPricingSnapshot(
            region=EIA_CALIFORNIA_REGION,
            quotes=make_quotes(EIA_US_REGION),
            refreshed_at=REFRESHED_AT,
        )


def test_observation_after_refresh_is_rejected() -> None:
    with pytest.raises(ValueError, match="observation cannot follow"):
        make_snapshot(
            observed_on=date(2026, 10, 14),
        )


def test_cache_starts_empty() -> None:
    cache = EiaPricingSnapshotCache()

    assert cache.get(EIA_CALIFORNIA_REGION) is None
    assert cache.regions() == ()


def test_cache_stores_complete_snapshot() -> None:
    cache = EiaPricingSnapshotCache()
    snapshot = make_snapshot()

    cache.replace(snapshot)

    assert cache.get(EIA_CALIFORNIA_REGION) is snapshot
    assert cache.regions() == (EIA_CALIFORNIA_REGION,)


def test_california_and_national_snapshots_are_independent() -> None:
    cache = EiaPricingSnapshotCache()
    california = make_snapshot(EIA_CALIFORNIA_REGION)
    national = make_snapshot(EIA_US_REGION)

    cache.replace(california)
    cache.replace(national)

    assert cache.get(EIA_CALIFORNIA_REGION) is california
    assert cache.get(EIA_US_REGION) is national
    assert cache.regions() == (
        EIA_CALIFORNIA_REGION,
        EIA_US_REGION,
    )


def test_failed_replace_preserves_previous_snapshot() -> None:
    cache = EiaPricingSnapshotCache()
    previous = make_snapshot()
    cache.replace(previous)

    with pytest.raises(TypeError, match="EiaPricingSnapshot"):
        cache.replace("invalid")  # type: ignore[arg-type]

    assert cache.get(EIA_CALIFORNIA_REGION) is previous


def test_older_refresh_timestamp_cannot_replace_newer() -> None:
    cache = EiaPricingSnapshotCache()
    previous = make_snapshot()
    cache.replace(previous)

    older = make_snapshot(refreshed_at=datetime(2026, 10, 12, tzinfo=UTC))

    with pytest.raises(ValueError, match="refresh timestamp"):
        cache.replace(older)

    assert cache.get(EIA_CALIFORNIA_REGION) is previous


def test_older_observation_cannot_replace_newer() -> None:
    cache = EiaPricingSnapshotCache()
    previous = make_snapshot()
    cache.replace(previous)

    older = make_snapshot(
        observed_on=date(2026, 9, 28),
        refreshed_at=datetime(2026, 10, 14, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="observation date"):
        cache.replace(older)

    assert cache.get(EIA_CALIFORNIA_REGION) is previous


def test_repeated_observation_does_not_change_source_date() -> None:
    cache = EiaPricingSnapshotCache()
    cache.replace(make_snapshot())

    refreshed = make_snapshot(
        refreshed_at=datetime(2026, 10, 14, tzinfo=UTC),
    )
    cache.replace(refreshed)

    selected = cache.get(EIA_CALIFORNIA_REGION)

    assert selected is refreshed
    assert selected is not None
    assert selected.quotes[0].observed_at == datetime(2026, 10, 5, tzinfo=UTC)


def test_cache_does_not_apply_price_freshness() -> None:
    cache = EiaPricingSnapshotCache()
    snapshot = make_snapshot()
    cache.replace(snapshot)

    assert cache.get(EIA_CALIFORNIA_REGION) is snapshot
    assert snapshot.quotes[0].source is GasolinePriceSource.REGIONAL_MARKET
    assert snapshot.quotes[0].observed_at == datetime(2026, 10, 5, tzinfo=UTC)
