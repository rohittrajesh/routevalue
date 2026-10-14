"""M8 process-local Census resolver lifecycle tests."""

from collections.abc import Iterator

import pytest

from routevalue.application.gasoline_price_geography import (
    PricingJurisdiction,
)
from routevalue.application.models import ResolvedLocation
from routevalue.infrastructure.pricing.census_jurisdiction import (
    CensusPricingJurisdictionResolver,
)
from routevalue.infrastructure.pricing.census_resolver_lifecycle import (
    get_census_pricing_jurisdiction_resolver,
)


@pytest.fixture(autouse=True)
def reset_resolver_cache() -> Iterator[None]:
    """Ensure tests do not share cached resolver state."""
    get_census_pricing_jurisdiction_resolver.cache_clear()
    yield
    get_census_pricing_jurisdiction_resolver.cache_clear()


def test_first_call_creates_resolver() -> None:
    resolver = get_census_pricing_jurisdiction_resolver()

    assert isinstance(
        resolver,
        CensusPricingJurisdictionResolver,
    )


def test_repeated_calls_return_same_instance() -> None:
    first = get_census_pricing_jurisdiction_resolver()
    second = get_census_pricing_jurisdiction_resolver()
    third = get_census_pricing_jurisdiction_resolver()

    assert first is second
    assert second is third


def test_cache_records_one_miss_and_multiple_hits() -> None:
    get_census_pricing_jurisdiction_resolver()
    get_census_pricing_jurisdiction_resolver()
    get_census_pricing_jurisdiction_resolver()

    info = get_census_pricing_jurisdiction_resolver.cache_info()

    assert info.misses == 1
    assert info.hits == 2
    assert info.currsize == 1


def test_cache_clear_creates_new_instance() -> None:
    first = get_census_pricing_jurisdiction_resolver()

    get_census_pricing_jurisdiction_resolver.cache_clear()

    second = get_census_pricing_jurisdiction_resolver()

    assert first is not second


def test_cached_resolver_classifies_multiple_locations() -> None:
    resolver = get_census_pricing_jurisdiction_resolver()

    san_diego = ResolvedLocation(
        display_name="San Diego",
        latitude=32.7157,
        longitude=-117.1611,
    )

    las_vegas = ResolvedLocation(
        display_name="Las Vegas",
        latitude=36.1699,
        longitude=-115.1398,
    )

    assert resolver.resolve(san_diego).jurisdiction is PricingJurisdiction.CALIFORNIA

    assert resolver.resolve(las_vegas).jurisdiction is PricingJurisdiction.OTHER_US

    assert get_census_pricing_jurisdiction_resolver() is resolver


def test_cache_starts_empty_after_reset() -> None:
    info = get_census_pricing_jurisdiction_resolver.cache_info()

    assert info.hits == 0
    assert info.misses == 0
    assert info.currsize == 0
