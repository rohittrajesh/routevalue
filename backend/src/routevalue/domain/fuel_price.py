"""Pure fuel-price policy for RouteValue."""

from datetime import datetime, timedelta

from routevalue.domain.models import (
    FuelPriceQuote,
    FuelPriceSource,
    GasolineGrade,
)

LOCAL_MARKET_MAX_AGE = timedelta(hours=48)
REGIONAL_MARKET_MAX_AGE = timedelta(days=7)


def _require_timezone_aware(value: datetime, *, name: str) -> None:
    """Require a timezone-aware datetime."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _validate_quote_source(
    quote: FuelPriceQuote,
    *,
    expected_source: FuelPriceSource,
    argument_name: str,
) -> None:
    """Require a quote to match the source represented by its argument."""

    if quote.source is not expected_source:
        raise ValueError(f"{argument_name} must use FuelPriceSource.{expected_source.name}")


def is_fuel_price_quote_fresh(
    quote: FuelPriceQuote,
    *,
    as_of: datetime,
) -> bool:
    """Return whether a fuel-price quote is usable under the V1 freshness policy."""

    _require_timezone_aware(as_of, name="as_of")

    if quote.source is FuelPriceSource.USER_OVERRIDE:
        return True

    if quote.observed_at is None:
        raise ValueError("market fuel price requires an observation timestamp")

    age = as_of - quote.observed_at

    if age < timedelta(0):
        return False

    if quote.source is FuelPriceSource.LOCAL_MARKET:
        return age <= LOCAL_MARKET_MAX_AGE

    if quote.source is FuelPriceSource.REGIONAL_MARKET:
        return age <= REGIONAL_MARKET_MAX_AGE

    raise ValueError("unsupported fuel price source")


def resolve_fuel_price_quote(
    *,
    fuel_grade: GasolineGrade,
    as_of: datetime,
    user_override: FuelPriceQuote | None = None,
    local_market_quote: FuelPriceQuote | None = None,
    regional_market_quote: FuelPriceQuote | None = None,
) -> FuelPriceQuote | None:
    """Resolve the highest-precedence usable fuel-price quote."""

    _require_timezone_aware(as_of, name="as_of")

    if user_override is not None:
        _validate_quote_source(
            user_override,
            expected_source=FuelPriceSource.USER_OVERRIDE,
            argument_name="user_override",
        )

    if local_market_quote is not None:
        _validate_quote_source(
            local_market_quote,
            expected_source=FuelPriceSource.LOCAL_MARKET,
            argument_name="local_market_quote",
        )

    if regional_market_quote is not None:
        _validate_quote_source(
            regional_market_quote,
            expected_source=FuelPriceSource.REGIONAL_MARKET,
            argument_name="regional_market_quote",
        )

    if user_override is not None and user_override.fuel_grade is fuel_grade:
        return user_override

    if (
        local_market_quote is not None
        and local_market_quote.fuel_grade is fuel_grade
        and is_fuel_price_quote_fresh(local_market_quote, as_of=as_of)
    ):
        return local_market_quote

    if (
        regional_market_quote is not None
        and regional_market_quote.fuel_grade is fuel_grade
        and is_fuel_price_quote_fresh(regional_market_quote, as_of=as_of)
    ):
        return regional_market_quote

    return None
