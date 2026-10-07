from datetime import UTC, datetime
from decimal import Decimal

import pytest

from routevalue.domain.models import (
    ElectricityPriceQuote,
    FuelPriceQuote,
    FuelPriceSource,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
)


def test_gasoline_price_quote_accepts_user_override() -> None:
    quote = GasolinePriceQuote(
        price_per_gallon=Decimal("4.59"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    assert quote.price_per_gallon == Decimal("4.59")
    assert quote.fuel_grade is GasolineGrade.PREMIUM
    assert quote.source is GasolinePriceSource.USER_OVERRIDE
    assert quote.observed_at is None


def test_gasoline_price_quote_accepts_market_price() -> None:
    observed_at = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

    quote = GasolinePriceQuote(
        price_per_gallon=Decimal("4.39"),
        fuel_grade=GasolineGrade.REGULAR,
        source=GasolinePriceSource.LOCAL_MARKET,
        observed_at=observed_at,
    )

    assert quote.observed_at == observed_at


def test_gasoline_price_quote_rejects_negative_price() -> None:
    with pytest.raises(
        ValueError,
        match="price_per_gallon cannot be negative",
    ):
        GasolinePriceQuote(
            price_per_gallon=Decimal("-0.01"),
            fuel_grade=GasolineGrade.REGULAR,
            source=GasolinePriceSource.USER_OVERRIDE,
            observed_at=None,
        )


def test_gasoline_market_price_requires_timestamp() -> None:
    with pytest.raises(
        ValueError,
        match="market fuel price requires an observation timestamp",
    ):
        GasolinePriceQuote(
            price_per_gallon=Decimal("4.39"),
            fuel_grade=GasolineGrade.REGULAR,
            source=GasolinePriceSource.LOCAL_MARKET,
            observed_at=None,
        )


def test_legacy_fuel_price_names_are_gasoline_compatibility_aliases() -> None:
    assert FuelPriceQuote is GasolinePriceQuote
    assert FuelPriceSource is GasolinePriceSource


def test_electricity_price_quote_accepts_positive_price() -> None:
    quote = ElectricityPriceQuote(
        price_per_kilowatt_hour=Decimal("0.315"),
    )

    assert quote.price_per_kilowatt_hour == Decimal("0.315")


def test_electricity_price_quote_allows_zero_price() -> None:
    quote = ElectricityPriceQuote(
        price_per_kilowatt_hour=Decimal(0),
    )

    assert quote.price_per_kilowatt_hour == Decimal(0)


def test_electricity_price_quote_rejects_negative_price() -> None:
    with pytest.raises(
        ValueError,
        match="price_per_kilowatt_hour cannot be negative",
    ):
        ElectricityPriceQuote(
            price_per_kilowatt_hour=Decimal("-0.001"),
        )
