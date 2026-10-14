"""Deterministic selection of a usable gasoline price quote."""

from datetime import datetime

from routevalue.application.gasoline_price_failures import (
    GasolinePriceUnavailableError,
    GasolinePriceUnavailableReason,
)
from routevalue.domain.fuel_price import (
    is_fuel_price_quote_fresh,
)
from routevalue.domain.gasoline_price_metadata import (
    GasolinePriceGeography,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
)


def select_gasoline_price_quote(
    *,
    fuel_grade: GasolineGrade,
    geography: GasolinePriceGeography,
    as_of: datetime,
    user_override: GasolinePriceQuote | None = None,
    market_quote: GasolinePriceQuote | None = None,
) -> GasolinePriceQuote:
    """Select one validated price without external lookups.

    A grade-matched manual override takes precedence.

    Automatic market quotes require matching grade, geographic
    provenance, supported market source, and valid freshness.

    Geographic fallback belongs to separate orchestration.
    """

    if not isinstance(fuel_grade, GasolineGrade):
        raise TypeError("fuel_grade must be a GasolineGrade")

    if not isinstance(geography, GasolinePriceGeography):
        raise TypeError("geography must be a GasolinePriceGeography")

    if not isinstance(as_of, datetime):
        raise TypeError("as_of must be a datetime")

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")

    if user_override is not None:
        if not isinstance(user_override, GasolinePriceQuote):
            raise TypeError("user_override must be a GasolinePriceQuote")

        if user_override.source is not GasolinePriceSource.USER_OVERRIDE:
            raise ValueError("user_override must use USER_OVERRIDE source")

        if user_override.fuel_grade is not fuel_grade:
            raise GasolinePriceUnavailableError(GasolinePriceUnavailableReason.GRADE_MISMATCH)

        return user_override

    if market_quote is None:
        raise GasolinePriceUnavailableError(GasolinePriceUnavailableReason.PRICE_NOT_FOUND)

    if not isinstance(market_quote, GasolinePriceQuote):
        raise GasolinePriceUnavailableError(GasolinePriceUnavailableReason.INVALID_QUOTE)

    if market_quote.source not in (
        GasolinePriceSource.LOCAL_MARKET,
        GasolinePriceSource.REGIONAL_MARKET,
    ):
        raise GasolinePriceUnavailableError(GasolinePriceUnavailableReason.INVALID_QUOTE)

    if market_quote.fuel_grade is not fuel_grade:
        raise GasolinePriceUnavailableError(GasolinePriceUnavailableReason.GRADE_MISMATCH)

    metadata = market_quote.market_metadata

    if metadata is None:
        raise GasolinePriceUnavailableError(GasolinePriceUnavailableReason.INVALID_QUOTE)

    if metadata.geography != geography:
        raise GasolinePriceUnavailableError(GasolinePriceUnavailableReason.GEOGRAPHY_MISMATCH)

    if not is_fuel_price_quote_fresh(
        market_quote,
        as_of=as_of,
    ):
        raise GasolinePriceUnavailableError(GasolinePriceUnavailableReason.PRICE_STALE)

    return market_quote
