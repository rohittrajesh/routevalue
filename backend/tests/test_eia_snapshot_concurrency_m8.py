"""Concurrent and correction-safety tests for EIA snapshot caching."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Barrier

import pytest

from routevalue.domain.models import GasolineGrade
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

BASE_REFRESH = datetime(2026, 10, 13, tzinfo=UTC)
BASE_OBSERVATION = date(2026, 10, 5)


def make_snapshot(
    *,
    region: EiaGasolineRegion = EIA_CALIFORNIA_REGION,
    observed_on: date = BASE_OBSERVATION,
    refreshed_at: datetime = BASE_REFRESH,
    price: str = "5.123",
) -> EiaPricingSnapshot:
    observations = tuple(
        EiaGasolineObservation(
            series_id=region.series_for_grade(grade),
            fuel_grade=grade,
            observed_on=observed_on,
            price_per_gallon=Decimal(price),
        )
        for grade in GasolineGrade
    )

    return EiaPricingSnapshot(
        region=region,
        quotes=normalize_eia_observations(
            observations=observations,
            region=region,
        ),
        refreshed_at=refreshed_at,
    )


def test_conflicting_same_date_price_is_rejected() -> None:
    cache = EiaPricingSnapshotCache()
    previous = make_snapshot()
    cache.replace(previous)

    conflicting = make_snapshot(
        refreshed_at=BASE_REFRESH + timedelta(hours=1),
        price="5.999",
    )

    with pytest.raises(ValueError, match="conflicting EIA price"):
        cache.replace(conflicting)

    assert cache.get(EIA_CALIFORNIA_REGION) is previous


def test_identical_observation_can_be_refreshed() -> None:
    cache = EiaPricingSnapshotCache()
    cache.replace(make_snapshot())

    refreshed = make_snapshot(
        refreshed_at=BASE_REFRESH + timedelta(hours=1),
    )
    cache.replace(refreshed)

    assert cache.get(EIA_CALIFORNIA_REGION) is refreshed


def test_newer_observation_can_change_price() -> None:
    cache = EiaPricingSnapshotCache()
    cache.replace(make_snapshot())

    newer = make_snapshot(
        observed_on=date(2026, 10, 12),
        refreshed_at=BASE_REFRESH + timedelta(hours=1),
        price="5.999",
    )
    cache.replace(newer)

    assert cache.get(EIA_CALIFORNIA_REGION) is newer


def test_california_replacement_does_not_change_national() -> None:
    cache = EiaPricingSnapshotCache()

    national = make_snapshot(
        region=EIA_US_REGION,
        price="4.354",
    )

    cache.replace(national)
    cache.replace(make_snapshot())

    california_new = make_snapshot(
        observed_on=date(2026, 10, 12),
        refreshed_at=BASE_REFRESH + timedelta(hours=1),
        price="6.227",
    )

    cache.replace(california_new)

    assert cache.get(EIA_US_REGION) is national
    assert cache.get(EIA_CALIFORNIA_REGION) is california_new


def test_concurrent_readers_never_see_partial_snapshot() -> None:
    cache = EiaPricingSnapshotCache()
    cache.replace(make_snapshot())

    start = Barrier(5)

    def writer() -> None:
        start.wait()

        for index in range(1, 51):
            snapshot = make_snapshot(
                refreshed_at=BASE_REFRESH + timedelta(seconds=index),
            )
            cache.replace(snapshot)

    def reader() -> int:
        start.wait()
        checked = 0

        for _ in range(200):
            snapshot = cache.get(EIA_CALIFORNIA_REGION)

            assert snapshot is not None
            assert len(snapshot.quotes) == 3
            assert {quote.fuel_grade for quote in snapshot.quotes} == set(GasolineGrade)

            assert all(quote.price_per_gallon == Decimal("5.123") for quote in snapshot.quotes)

            checked += 1

        return checked

    with ThreadPoolExecutor(max_workers=5) as executor:
        writer_future = executor.submit(writer)
        reader_futures = [executor.submit(reader) for _ in range(4)]

        writer_future.result(timeout=10)

        totals = [future.result(timeout=10) for future in reader_futures]

    assert sum(totals) == 800

    final = cache.get(EIA_CALIFORNIA_REGION)
    assert final is not None
    assert final.refreshed_at == BASE_REFRESH + timedelta(seconds=50)


def test_concurrent_regressing_updates_are_rejected() -> None:
    cache = EiaPricingSnapshotCache()

    newest = make_snapshot(
        refreshed_at=BASE_REFRESH + timedelta(days=2),
    )
    cache.replace(newest)

    def attempt_older(index: int) -> bool:
        older = make_snapshot(
            refreshed_at=BASE_REFRESH + timedelta(seconds=index),
        )

        try:
            cache.replace(older)
        except ValueError:
            return True

        return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(attempt_older, range(40)))

    assert all(results)
    assert cache.get(EIA_CALIFORNIA_REGION) is newest
