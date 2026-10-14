"""M8 metric Census jurisdiction boundary regression tests."""

import pytest
from shapely.geometry import Polygon  # type: ignore[import-untyped]

from routevalue.application.gasoline_price_geography import (
    PricingJurisdiction,
)
from routevalue.application.models import ResolvedLocation
from routevalue.infrastructure.pricing.census_jurisdiction import (
    BOUNDARY_TOLERANCE_METERS,
    CensusPricingJurisdictionResolver,
)


def make_location(
    longitude: float,
    latitude: float,
) -> ResolvedLocation:
    return ResolvedLocation(
        display_name="Synthetic Test Location",
        latitude=latitude,
        longitude=longitude,
    )


def make_resolver(
    states: tuple[tuple[str, Polygon], ...],
) -> CensusPricingJurisdictionResolver:
    resolver = CensusPricingJurisdictionResolver.__new__(CensusPricingJurisdictionResolver)
    resolver._states = states
    return resolver


def square(
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
) -> Polygon:
    return Polygon(
        [
            (xmin, ymin),
            (xmax, ymin),
            (xmax, ymax),
            (xmin, ymax),
        ]
    )


def test_metric_tolerance_is_250_meters() -> None:
    assert BOUNDARY_TOLERANCE_METERS == 250.0


def test_clear_california_interior() -> None:
    resolver = make_resolver((("CA", square(0, 0, 10, 10)),))

    result = resolver.resolve(make_location(5, 5))

    assert result.jurisdiction is PricingJurisdiction.CALIFORNIA


def test_clear_other_state_interior() -> None:
    resolver = make_resolver((("NV", square(0, 0, 10, 10)),))

    result = resolver.resolve(make_location(5, 5))

    assert result.jurisdiction is PricingJurisdiction.OTHER_US


@pytest.mark.parametrize(
    ("longitude", "latitude"),
    [
        (0, 5),
        (10, 5),
        (5, 0),
        (5, 10),
        (0, 0),
        (10, 10),
    ],
)
def test_exact_boundary_is_unknown(
    longitude: float,
    latitude: float,
) -> None:
    resolver = make_resolver((("CA", square(0, 0, 10, 10)),))

    assert (
        resolver.resolve(make_location(longitude, latitude)).jurisdiction
        is PricingJurisdiction.UNKNOWN
    )


def test_approximately_111_meters_inside_is_unknown() -> None:
    resolver = make_resolver((("CA", square(0, 0, 10, 10)),))

    result = resolver.resolve(make_location(0.001, 5))

    assert result.jurisdiction is PricingJurisdiction.UNKNOWN


def test_approximately_333_meters_inside_is_california() -> None:
    resolver = make_resolver((("CA", square(0, 0, 10, 10)),))

    result = resolver.resolve(make_location(0.003, 5))

    assert result.jurisdiction is PricingJurisdiction.CALIFORNIA


def test_outside_boundary_is_unknown() -> None:
    resolver = make_resolver((("CA", square(0, 0, 10, 10)),))

    result = resolver.resolve(make_location(-0.001, 5))

    assert result.jurisdiction is PricingJurisdiction.UNKNOWN


def test_unmatched_location_is_unknown() -> None:
    resolver = make_resolver((("CA", square(0, 0, 10, 10)),))

    result = resolver.resolve(make_location(20, 20))

    assert result.jurisdiction is PricingJurisdiction.UNKNOWN


def test_overlapping_polygons_are_unknown() -> None:
    resolver = make_resolver(
        (
            ("CA", square(0, 0, 10, 10)),
            ("NV", square(4, 4, 14, 14)),
        )
    )

    result = resolver.resolve(make_location(7, 7))

    assert result.jurisdiction is PricingJurisdiction.UNKNOWN


def test_shared_border_within_tolerance_is_unknown() -> None:
    resolver = make_resolver(
        (
            ("CA", square(0, 0, 10, 10)),
            ("NV", square(10, 0, 20, 10)),
        )
    )

    result = resolver.resolve(make_location(9.999, 5))

    assert result.jurisdiction is PricingJurisdiction.UNKNOWN


def test_distant_polygon_does_not_interfere() -> None:
    resolver = make_resolver(
        (
            ("CA", square(0, 0, 10, 10)),
            ("NV", square(20, 20, 30, 30)),
        )
    )

    result = resolver.resolve(make_location(5, 5))

    assert result.jurisdiction is PricingJurisdiction.CALIFORNIA


def test_display_name_does_not_override_coordinates() -> None:
    resolver = make_resolver((("NV", square(0, 0, 10, 10)),))

    location = ResolvedLocation(
        display_name="Los Angeles, California",
        latitude=5,
        longitude=5,
    )

    result = resolver.resolve(location)

    assert result.jurisdiction is PricingJurisdiction.OTHER_US
