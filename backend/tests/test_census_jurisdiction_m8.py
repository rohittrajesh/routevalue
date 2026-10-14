"""M8 Census-based jurisdiction integration tests."""

from pathlib import Path

import pytest

from routevalue.application.gasoline_price_geography import (
    PricingJurisdiction,
)
from routevalue.application.models import ResolvedLocation
from routevalue.infrastructure.pricing.census_jurisdiction import (
    DEFAULT_BOUNDARY_ARCHIVE,
    CensusPricingJurisdictionResolver,
)


@pytest.fixture(scope="module")
def resolver() -> CensusPricingJurisdictionResolver:
    return CensusPricingJurisdictionResolver()


def make_location(
    latitude: float,
    longitude: float,
    name: str,
) -> ResolvedLocation:
    return ResolvedLocation(
        display_name=name,
        latitude=latitude,
        longitude=longitude,
    )


@pytest.mark.parametrize(
    ("name", "latitude", "longitude", "expected"),
    [
        (
            "San Diego",
            32.7157,
            -117.1611,
            PricingJurisdiction.CALIFORNIA,
        ),
        (
            "Los Angeles",
            34.0522,
            -118.2437,
            PricingJurisdiction.CALIFORNIA,
        ),
        (
            "Sacramento",
            38.5816,
            -121.4944,
            PricingJurisdiction.CALIFORNIA,
        ),
        (
            "Las Vegas",
            36.1699,
            -115.1398,
            PricingJurisdiction.OTHER_US,
        ),
        (
            "Phoenix",
            33.4484,
            -112.0740,
            PricingJurisdiction.OTHER_US,
        ),
        (
            "Austin",
            30.2672,
            -97.7431,
            PricingJurisdiction.OTHER_US,
        ),
        (
            "Honolulu",
            21.3099,
            -157.8583,
            PricingJurisdiction.OTHER_US,
        ),
        (
            "Toronto",
            43.6532,
            -79.3832,
            PricingJurisdiction.UNKNOWN,
        ),
        (
            "Pacific Ocean",
            36.0,
            -125.5,
            PricingJurisdiction.UNKNOWN,
        ),
    ],
)
def test_coordinate_classification(
    resolver: CensusPricingJurisdictionResolver,
    name: str,
    latitude: float,
    longitude: float,
    expected: PricingJurisdiction,
) -> None:
    location = make_location(
        latitude,
        longitude,
        name,
    )

    result = resolver.resolve(location)

    assert result.jurisdiction is expected


def test_display_name_cannot_override_coordinates(
    resolver: CensusPricingJurisdictionResolver,
) -> None:
    location = make_location(
        36.1699,
        -115.1398,
        "California",
    )

    result = resolver.resolve(location)

    assert result.jurisdiction is PricingJurisdiction.OTHER_US


def test_repeated_classification_is_deterministic(
    resolver: CensusPricingJurisdictionResolver,
) -> None:
    location = make_location(
        32.7157,
        -117.1611,
        "San Diego",
    )

    first = resolver.resolve(location)
    second = resolver.resolve(location)

    assert first == second


def test_packaged_dataset_exists() -> None:
    assert DEFAULT_BOUNDARY_ARCHIVE.is_file()


def test_missing_dataset_is_rejected(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing.zip"

    with pytest.raises(FileNotFoundError):
        CensusPricingJurisdictionResolver(
            archive_path=missing_path,
        )


def test_invalid_location_type_is_rejected(
    resolver: CensusPricingJurisdictionResolver,
) -> None:
    with pytest.raises(TypeError, match="ResolvedLocation"):
        resolver.resolve(
            "San Diego"  # type: ignore[arg-type]
        )
