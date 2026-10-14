"""Bounded, deterministic geographic fallback for gasoline pricing."""

from dataclasses import dataclass
from datetime import datetime

from routevalue.application.gasoline_price_failures import (
    GasolinePriceUnavailableError,
    GasolinePriceUnavailableReason,
)
from routevalue.application.gasoline_price_ports import (
    GasolinePriceLookupRequest,
    GasolinePriceProvider,
)
from routevalue.application.gasoline_price_selection import (
    select_gasoline_price_quote,
)
from routevalue.domain.gasoline_price_metadata import (
    GasolinePriceGeographicScope,
    GasolinePriceGeography,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
)

MAX_GEOGRAPHIC_LOOKUPS = 5

_SCOPE_ORDER: dict[GasolinePriceGeographicScope, int] = {
    GasolinePriceGeographicScope.STATION: 0,
    GasolinePriceGeographicScope.METRO: 1,
    GasolinePriceGeographicScope.STATE: 2,
    GasolinePriceGeographicScope.REGION: 3,
    GasolinePriceGeographicScope.NATIONAL: 4,
}


@dataclass(frozen=True, slots=True)
class GasolinePriceFallbackPlan:
    """An explicitly ordered sequence of eligible pricing geographies.

    The caller must verify that each broader geography actually
    covers the intended pricing reference location.

    This model validates ordering and bounds, not geographic
    containment. Provider-specific mapping belongs elsewhere.
    """

    geographies: tuple[GasolinePriceGeography, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.geographies, tuple):
            raise TypeError("geographies must be a tuple")

        if not self.geographies:
            raise ValueError("fallback plan cannot be empty")

        if len(self.geographies) > MAX_GEOGRAPHIC_LOOKUPS:
            raise ValueError("too many geographic lookups")

        seen: set[tuple[GasolinePriceGeographicScope, str]] = set()
        previous_rank = -1

        for geography in self.geographies:
            if not isinstance(geography, GasolinePriceGeography):
                raise TypeError("fallback entries must be GasolinePriceGeography")

            identity = (geography.scope, geography.region_id)

            if identity in seen:
                raise ValueError("duplicate pricing geography")

            seen.add(identity)

            rank = _SCOPE_ORDER[geography.scope]

            if rank <= previous_rank:
                raise ValueError("fallback geographies must progress from specific to broad")

            previous_rank = rank


def resolve_geographic_gasoline_price(
    *,
    provider: GasolinePriceProvider,
    fuel_grade: GasolineGrade,
    plan: GasolinePriceFallbackPlan,
    as_of: datetime,
    user_override: GasolinePriceQuote | None = None,
) -> GasolinePriceQuote:
    """Resolve a price using bounded, explicit geographic fallback.

    Manual overrides always bypass external lookup.

    Missing, stale, or unsupported market observations permit
    fallback. Provider operational failures and invalid quotes
    terminate resolution rather than being silently ignored.
    """

    if not isinstance(fuel_grade, GasolineGrade):
        raise TypeError("fuel_grade must be a GasolineGrade")

    if not isinstance(plan, GasolinePriceFallbackPlan):
        raise TypeError("plan must be a GasolinePriceFallbackPlan")

    if not isinstance(as_of, datetime):
        raise TypeError("as_of must be a datetime")

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")

    if user_override is not None:
        return select_gasoline_price_quote(
            fuel_grade=fuel_grade,
            geography=plan.geographies[0],
            as_of=as_of,
            user_override=user_override,
        )

    stale_found = False
    unsupported_grade_found = False
    unsupported_geography_found = False

    for geography in plan.geographies:
        request = GasolinePriceLookupRequest(
            fuel_grade=fuel_grade,
            geography=geography,
        )

        try:
            quote = provider.get_price(request)
        except GasolinePriceUnavailableError as exc:
            if exc.reason is GasolinePriceUnavailableReason.UNSUPPORTED_GEOGRAPHY:
                unsupported_geography_found = True
                continue

            if exc.reason is GasolinePriceUnavailableReason.UNSUPPORTED_GRADE:
                unsupported_grade_found = True
                continue

            raise

        if quote is None:
            continue

        try:
            return select_gasoline_price_quote(
                fuel_grade=fuel_grade,
                geography=geography,
                as_of=as_of,
                market_quote=quote,
            )
        except GasolinePriceUnavailableError as exc:
            if exc.reason is GasolinePriceUnavailableReason.PRICE_STALE:
                stale_found = True
                continue

            raise

    if stale_found:
        reason = GasolinePriceUnavailableReason.PRICE_STALE
    elif unsupported_grade_found:
        reason = GasolinePriceUnavailableReason.UNSUPPORTED_GRADE
    elif unsupported_geography_found:
        reason = GasolinePriceUnavailableReason.UNSUPPORTED_GEOGRAPHY
    else:
        reason = GasolinePriceUnavailableReason.PRICE_NOT_FOUND

    raise GasolinePriceUnavailableError(reason)
