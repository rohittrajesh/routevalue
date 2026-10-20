"""Resolve automatic trip gasoline pricing from persisted EIA observations."""

from datetime import datetime

from routevalue.application.gasoline_price_fallback import (
    resolve_geographic_gasoline_price,
)
from routevalue.application.gasoline_price_geography import (
    PricingJurisdictionResolver,
)
from routevalue.application.gasoline_price_ports import (
    GasolinePriceProvider,
)
from routevalue.application.models import ResolvedLocation
from routevalue.domain.models import GasolineGrade, GasolinePriceQuote
from routevalue.infrastructure.pricing.eia_reference_resolution import (
    resolve_eia_pricing_geography,
)
from routevalue.infrastructure.pricing.eia_release_policy import is_eia_weekly_quote_fresh


def resolve_persisted_eia_gasoline_price(
    *,
    provider: GasolinePriceProvider,
    jurisdiction_resolver: PricingJurisdictionResolver,
    origin: ResolvedLocation,
    fuel_grade: GasolineGrade,
    as_of: datetime,
) -> GasolinePriceQuote:
    """Resolve one automatic gasoline price for a trusted trip origin.

    Geography is determined by the injected trusted resolver, not
    by origin display names or user-provided region identifiers.

    The EIA mapping permits only approved geographic fallback.
    The application fallback layer enforces quote freshness,
    matching fuel grade, and pricing provenance.

    This function never downloads EIA data, modifies persistent
    snapshots, or supplies an invented fallback price.
    """

    geography = resolve_eia_pricing_geography(
        resolver=jurisdiction_resolver,
        location=origin,
    )

    return resolve_geographic_gasoline_price(
        provider=provider,
        fuel_grade=fuel_grade,
        plan=geography.fallback_plan,
        as_of=as_of,
        freshness_policy=is_eia_weekly_quote_fresh,
    )
