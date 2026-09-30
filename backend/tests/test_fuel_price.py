from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from routevalue.domain.fuel_price import (
    is_fuel_price_quote_fresh,
    resolve_fuel_price_quote,
)
from routevalue.domain.models import (
    FuelPriceQuote,
    FuelPriceSource,
    GasolineGrade,
)


def test_user_override_is_not_subject_to_freshness_expiration() -> None:
    quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.25"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    assert is_fuel_price_quote_fresh(
        quote,
        as_of=datetime(2026, 9, 29, 12, 0, tzinfo=UTC),
    )


def test_local_market_quote_within_48_hours_is_fresh() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.59"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=as_of - timedelta(hours=47),
    )

    assert is_fuel_price_quote_fresh(quote, as_of=as_of)


def test_local_market_quote_exactly_48_hours_old_is_fresh() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.59"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=as_of - timedelta(hours=48),
    )

    assert is_fuel_price_quote_fresh(quote, as_of=as_of)


def test_local_market_quote_older_than_48_hours_is_stale() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.59"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=as_of - timedelta(hours=48, seconds=1),
    )

    assert not is_fuel_price_quote_fresh(quote, as_of=as_of)


def test_regional_market_quote_exactly_7_days_old_is_fresh() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.39"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.REGIONAL_MARKET,
        observed_at=as_of - timedelta(days=7),
    )

    assert is_fuel_price_quote_fresh(quote, as_of=as_of)


def test_regional_market_quote_older_than_7_days_is_stale() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.39"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.REGIONAL_MARKET,
        observed_at=as_of - timedelta(days=7, seconds=1),
    )

    assert not is_fuel_price_quote_fresh(quote, as_of=as_of)


def test_future_market_quote_is_not_fresh() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.59"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=as_of + timedelta(seconds=1),
    )

    assert not is_fuel_price_quote_fresh(quote, as_of=as_of)


def test_fuel_price_freshness_requires_timezone_aware_as_of() -> None:
    quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.25"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    with pytest.raises(ValueError, match="as_of must be timezone-aware"):
        is_fuel_price_quote_fresh(
            quote,
            as_of=datetime(2026, 9, 29, 12, 0),  # noqa: DTZ001
        )


def test_user_override_takes_precedence_over_market_quotes() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    override = FuelPriceQuote(
        price_per_gallon=Decimal("4.10"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )
    local = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=as_of - timedelta(hours=1),
    )
    regional = FuelPriceQuote(
        price_per_gallon=Decimal("4.30"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.REGIONAL_MARKET,
        observed_at=as_of - timedelta(days=1),
    )

    result = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.REGULAR,
        as_of=as_of,
        user_override=override,
        local_market_quote=local,
        regional_market_quote=regional,
    )

    assert result is override


def test_wrong_grade_user_override_falls_back_to_local_market() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    override = FuelPriceQuote(
        price_per_gallon=Decimal("4.10"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )
    local = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=as_of - timedelta(hours=1),
    )

    result = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.REGULAR,
        as_of=as_of,
        user_override=override,
        local_market_quote=local,
    )

    assert result is local


def test_local_market_takes_precedence_over_regional_market() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    local = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=as_of - timedelta(hours=24),
    )
    regional = FuelPriceQuote(
        price_per_gallon=Decimal("4.30"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.REGIONAL_MARKET,
        observed_at=as_of - timedelta(days=1),
    )

    result = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.REGULAR,
        as_of=as_of,
        local_market_quote=local,
        regional_market_quote=regional,
    )

    assert result is local


def test_stale_local_market_falls_back_to_regional_market() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    local = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=as_of - timedelta(hours=49),
    )
    regional = FuelPriceQuote(
        price_per_gallon=Decimal("4.30"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.REGIONAL_MARKET,
        observed_at=as_of - timedelta(days=1),
    )

    result = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.REGULAR,
        as_of=as_of,
        local_market_quote=local,
        regional_market_quote=regional,
    )

    assert result is regional


def test_wrong_grade_local_market_falls_back_to_regional_market() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    local = FuelPriceQuote(
        price_per_gallon=Decimal("5.10"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=as_of - timedelta(hours=1),
    )
    regional = FuelPriceQuote(
        price_per_gallon=Decimal("4.30"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.REGIONAL_MARKET,
        observed_at=as_of - timedelta(days=1),
    )

    result = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.REGULAR,
        as_of=as_of,
        local_market_quote=local,
        regional_market_quote=regional,
    )

    assert result is regional


def test_stale_regional_market_results_in_unavailable_price() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    regional = FuelPriceQuote(
        price_per_gallon=Decimal("4.30"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.REGIONAL_MARKET,
        observed_at=as_of - timedelta(days=8),
    )

    result = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.REGULAR,
        as_of=as_of,
        regional_market_quote=regional,
    )

    assert result is None


def test_missing_fuel_price_quotes_results_in_unavailable_price() -> None:
    result = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.REGULAR,
        as_of=datetime(2026, 9, 29, 12, 0, tzinfo=UTC),
    )

    assert result is None


def test_all_wrong_grade_quotes_result_in_unavailable_price() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    override = FuelPriceQuote(
        price_per_gallon=Decimal("5.00"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )
    local = FuelPriceQuote(
        price_per_gallon=Decimal("5.10"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=as_of - timedelta(hours=1),
    )
    regional = FuelPriceQuote(
        price_per_gallon=Decimal("4.90"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=FuelPriceSource.REGIONAL_MARKET,
        observed_at=as_of - timedelta(days=1),
    )

    result = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.REGULAR,
        as_of=as_of,
        user_override=override,
        local_market_quote=local,
        regional_market_quote=regional,
    )

    assert result is None


def test_resolver_rejects_quote_in_wrong_source_slot() -> None:
    quote = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=datetime(2026, 9, 29, 11, 0, tzinfo=UTC),
    )

    with pytest.raises(
        ValueError,
        match="user_override must use FuelPriceSource.USER_OVERRIDE",
    ):
        resolve_fuel_price_quote(
            fuel_grade=GasolineGrade.REGULAR,
            as_of=datetime(2026, 9, 29, 12, 0, tzinfo=UTC),
            user_override=quote,
        )


def test_resolver_requires_timezone_aware_as_of() -> None:
    with pytest.raises(ValueError, match="as_of must be timezone-aware"):
        resolve_fuel_price_quote(
            fuel_grade=GasolineGrade.REGULAR,
            as_of=datetime(2026, 9, 29, 12, 0),  # noqa: DTZ001
        )
