"""M8 trusted gasoline pricing jurisdiction tests."""

import pytest

from routevalue.application.gasoline_price_geography import (
    PricingGeographyUnavailableError,
    PricingGeographyUnavailableReason,
    PricingJurisdiction,
    PricingJurisdictionResult,
    resolve_pricing_jurisdiction,
)
from routevalue.application.models import ResolvedLocation


def make_location(
    display_name: str = "Example Location",
) -> ResolvedLocation:
    return ResolvedLocation(
        display_name=display_name,
        latitude=32.7157,
        longitude=-117.1611,
    )


class FakeJurisdictionResolver:
    """Explicit deterministic jurisdiction source."""

    def __init__(
        self,
        jurisdiction: PricingJurisdiction,
    ) -> None:
        self.jurisdiction = jurisdiction
        self.locations: list[ResolvedLocation] = []

    def resolve(
        self,
        location: ResolvedLocation,
    ) -> PricingJurisdictionResult:
        self.locations.append(location)
        return PricingJurisdictionResult(jurisdiction=self.jurisdiction)


@pytest.mark.parametrize(
    "jurisdiction",
    [
        PricingJurisdiction.CALIFORNIA,
        PricingJurisdiction.OTHER_US,
    ],
)
def test_supported_jurisdiction_is_returned(
    jurisdiction: PricingJurisdiction,
) -> None:
    resolver = FakeJurisdictionResolver(jurisdiction)

    assert (
        resolve_pricing_jurisdiction(
            resolver=resolver,
            location=make_location(),
        )
        is jurisdiction
    )


def test_outside_us_is_rejected() -> None:
    resolver = FakeJurisdictionResolver(PricingJurisdiction.OUTSIDE_US)

    with pytest.raises(PricingGeographyUnavailableError) as exc:
        resolve_pricing_jurisdiction(
            resolver=resolver,
            location=make_location(),
        )

    assert exc.value.reason is PricingGeographyUnavailableReason.OUTSIDE_SUPPORTED_COUNTRY


def test_unknown_jurisdiction_is_rejected() -> None:
    resolver = FakeJurisdictionResolver(PricingJurisdiction.UNKNOWN)

    with pytest.raises(PricingGeographyUnavailableError) as exc:
        resolve_pricing_jurisdiction(
            resolver=resolver,
            location=make_location(),
        )

    assert exc.value.reason is PricingGeographyUnavailableReason.JURISDICTION_UNKNOWN


def test_location_is_passed_unchanged() -> None:
    resolver = FakeJurisdictionResolver(PricingJurisdiction.CALIFORNIA)
    location = make_location()

    resolve_pricing_jurisdiction(
        resolver=resolver,
        location=location,
    )

    assert resolver.locations == [location]
    assert resolver.locations[0] is location


def test_display_name_does_not_override_jurisdiction() -> None:
    resolver = FakeJurisdictionResolver(PricingJurisdiction.OTHER_US)

    result = resolve_pricing_jurisdiction(
        resolver=resolver,
        location=make_location("California, USA"),
    )

    assert result is PricingJurisdiction.OTHER_US


def test_invalid_jurisdiction_is_rejected() -> None:
    with pytest.raises(TypeError, match="PricingJurisdiction"):
        PricingJurisdictionResult(
            jurisdiction="california"  # type: ignore[arg-type]
        )


def test_invalid_location_is_rejected() -> None:
    resolver = FakeJurisdictionResolver(PricingJurisdiction.CALIFORNIA)

    with pytest.raises(TypeError, match="ResolvedLocation"):
        resolve_pricing_jurisdiction(
            resolver=resolver,
            location="San Diego",  # type: ignore[arg-type]
        )

    assert resolver.locations == []


def test_invalid_resolver_result_is_rejected() -> None:
    class BrokenResolver:
        def resolve(
            self,
            location: ResolvedLocation,
        ) -> PricingJurisdictionResult:
            return "california"  # type: ignore[return-value]

    with pytest.raises(
        TypeError,
        match="PricingJurisdictionResult",
    ):
        resolve_pricing_jurisdiction(
            resolver=BrokenResolver(),
            location=make_location(),
        )


def test_resolution_is_deterministic() -> None:
    resolver = FakeJurisdictionResolver(PricingJurisdiction.CALIFORNIA)
    location = make_location()

    first = resolve_pricing_jurisdiction(
        resolver=resolver,
        location=location,
    )
    second = resolve_pricing_jurisdiction(
        resolver=resolver,
        location=location,
    )

    assert first is second
    assert first is PricingJurisdiction.CALIFORNIA


def test_geography_failure_preserves_reason() -> None:
    error = PricingGeographyUnavailableError(PricingGeographyUnavailableReason.JURISDICTION_UNKNOWN)

    assert error.reason is PricingGeographyUnavailableReason.JURISDICTION_UNKNOWN
    assert str(error) == "jurisdiction_unknown"
