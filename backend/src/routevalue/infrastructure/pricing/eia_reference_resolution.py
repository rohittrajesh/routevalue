"""Map trusted geographic jurisdictions to verified EIA pricing plans."""

from dataclasses import dataclass

from routevalue.application.gasoline_price_fallback import (
    GasolinePriceFallbackPlan,
)
from routevalue.application.gasoline_price_geography import (
    PricingJurisdiction,
    PricingJurisdictionResolver,
    resolve_pricing_jurisdiction,
)
from routevalue.application.models import ResolvedLocation
from routevalue.infrastructure.pricing.eia_geography import (
    EiaPricingReference,
    build_eia_fallback_plan,
)


@dataclass(frozen=True, slots=True)
class EiaPricingGeographyResult:
    """A verified pricing reference and its geographic fallback plan."""

    reference: EiaPricingReference
    fallback_plan: GasolinePriceFallbackPlan

    def __post_init__(self) -> None:
        if not isinstance(self.reference, EiaPricingReference):
            raise TypeError("reference must be an EiaPricingReference")

        if not isinstance(self.fallback_plan, GasolinePriceFallbackPlan):
            raise TypeError("fallback_plan must be a GasolinePriceFallbackPlan")

        expected = build_eia_fallback_plan(self.reference)

        if self.fallback_plan != expected:
            raise ValueError("fallback plan does not match verified EIA reference")


def map_jurisdiction_to_eia_reference(
    jurisdiction: PricingJurisdiction,
) -> EiaPricingReference:
    """Translate an established U.S. jurisdiction to EIA coverage."""

    if not isinstance(jurisdiction, PricingJurisdiction):
        raise TypeError("jurisdiction must be a PricingJurisdiction")

    if jurisdiction is PricingJurisdiction.CALIFORNIA:
        return EiaPricingReference.CALIFORNIA

    if jurisdiction is PricingJurisdiction.OTHER_US:
        return EiaPricingReference.UNITED_STATES

    raise ValueError("unsupported jurisdiction cannot map to an EIA reference")


def resolve_eia_pricing_geography(
    *,
    resolver: PricingJurisdictionResolver,
    location: ResolvedLocation,
) -> EiaPricingGeographyResult:
    """Build a verified EIA plan for a trusted pricing location.

    Unsupported or unknown locations are rejected by the
    application jurisdiction boundary before EIA mapping.

    No provider requests or coordinate heuristics are used.
    """

    jurisdiction = resolve_pricing_jurisdiction(
        resolver=resolver,
        location=location,
    )

    reference = map_jurisdiction_to_eia_reference(jurisdiction)

    return EiaPricingGeographyResult(
        reference=reference,
        fallback_plan=build_eia_fallback_plan(reference),
    )
