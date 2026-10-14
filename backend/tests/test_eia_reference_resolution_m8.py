"""M8 trusted jurisdiction-to-EIA geographic mapping tests."""

import pytest

from routevalue.application.gasoline_price_geography import (
    PricingGeographyUnavailableError,
    PricingGeographyUnavailableReason,
    PricingJurisdiction,
    PricingJurisdictionResult,
)
from routevalue.application.models import ResolvedLocation
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaPricingReference,
    build_eia_fallback_plan,
)
from routevalue.infrastructure.pricing.eia_reference_resolution import (
    EiaPricingGeographyResult,
    map_jurisdiction_to_eia_reference,
    resolve_eia_pricing_geography,
)


def make_location(
    name: str = "Example Location",
) -> ResolvedLocation:
    return ResolvedLocation(
        display_name=name,
        latitude=32.7157,
        longitude=-117.1611,
    )


class FakeResolver:
    def __init__(
        self,
        jurisdiction: PricingJurisdiction,
    ) -> None:
        self.jurisdiction = jurisdiction
        self.calls: list[ResolvedLocation] = []

    def resolve(
        self,
        location: ResolvedLocation,
    ) -> PricingJurisdictionResult:
        self.calls.append(location)
        return PricingJurisdictionResult(
            jurisdiction=self.jurisdiction,
        )


def test_california_maps_to_verified_reference() -> None:
    assert (
        map_jurisdiction_to_eia_reference(PricingJurisdiction.CALIFORNIA)
        is EiaPricingReference.CALIFORNIA
    )


def test_other_us_maps_to_national_reference() -> None:
    assert (
        map_jurisdiction_to_eia_reference(PricingJurisdiction.OTHER_US)
        is EiaPricingReference.UNITED_STATES
    )


@pytest.mark.parametrize(
    "jurisdiction",
    [
        PricingJurisdiction.OUTSIDE_US,
        PricingJurisdiction.UNKNOWN,
    ],
)
def test_unsupported_jurisdiction_cannot_map_directly(
    jurisdiction: PricingJurisdiction,
) -> None:
    with pytest.raises(ValueError, match="unsupported jurisdiction"):
        map_jurisdiction_to_eia_reference(jurisdiction)


def test_invalid_jurisdiction_type_is_rejected() -> None:
    with pytest.raises(TypeError, match="PricingJurisdiction"):
        map_jurisdiction_to_eia_reference(
            "california"  # type: ignore[arg-type]
        )


def test_california_resolution_builds_state_then_national() -> None:
    resolver = FakeResolver(PricingJurisdiction.CALIFORNIA)

    result = resolve_eia_pricing_geography(
        resolver=resolver,
        location=make_location(),
    )

    assert result.reference is EiaPricingReference.CALIFORNIA
    assert result.fallback_plan.geographies == (
        EIA_CALIFORNIA_REGION.geography,
        EIA_US_REGION.geography,
    )
    assert len(resolver.calls) == 1


def test_other_us_resolution_uses_national_only() -> None:
    resolver = FakeResolver(PricingJurisdiction.OTHER_US)

    result = resolve_eia_pricing_geography(
        resolver=resolver,
        location=make_location(),
    )

    assert result.reference is EiaPricingReference.UNITED_STATES
    assert result.fallback_plan.geographies == (EIA_US_REGION.geography,)
    assert len(resolver.calls) == 1


@pytest.mark.parametrize(
    ("jurisdiction", "reason"),
    [
        (
            PricingJurisdiction.OUTSIDE_US,
            PricingGeographyUnavailableReason.OUTSIDE_SUPPORTED_COUNTRY,
        ),
        (
            PricingJurisdiction.UNKNOWN,
            PricingGeographyUnavailableReason.JURISDICTION_UNKNOWN,
        ),
    ],
)
def test_unsupported_location_stops_before_mapping(
    jurisdiction: PricingJurisdiction,
    reason: PricingGeographyUnavailableReason,
) -> None:
    resolver = FakeResolver(jurisdiction)

    with pytest.raises(PricingGeographyUnavailableError) as exc:
        resolve_eia_pricing_geography(
            resolver=resolver,
            location=make_location(),
        )

    assert exc.value.reason is reason
    assert len(resolver.calls) == 1


def test_display_name_cannot_force_california_selection() -> None:
    resolver = FakeResolver(PricingJurisdiction.OTHER_US)

    result = resolve_eia_pricing_geography(
        resolver=resolver,
        location=make_location("Los Angeles, California"),
    )

    assert result.reference is EiaPricingReference.UNITED_STATES


def test_result_rejects_mismatched_fallback_plan() -> None:
    with pytest.raises(ValueError, match="does not match"):
        EiaPricingGeographyResult(
            reference=EiaPricingReference.CALIFORNIA,
            fallback_plan=build_eia_fallback_plan(EiaPricingReference.UNITED_STATES),
        )


def test_result_rejects_invalid_reference() -> None:
    with pytest.raises(TypeError, match="EiaPricingReference"):
        EiaPricingGeographyResult(
            reference="california",  # type: ignore[arg-type]
            fallback_plan=build_eia_fallback_plan(EiaPricingReference.CALIFORNIA),
        )


def test_reference_resolution_is_deterministic() -> None:
    resolver = FakeResolver(PricingJurisdiction.CALIFORNIA)
    location = make_location()

    first = resolve_eia_pricing_geography(
        resolver=resolver,
        location=location,
    )
    second = resolve_eia_pricing_geography(
        resolver=resolver,
        location=location,
    )

    assert first == second
    assert len(resolver.calls) == 2
