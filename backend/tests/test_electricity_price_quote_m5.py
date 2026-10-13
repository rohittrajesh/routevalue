"""M5 tests for finite, nonnegative electricity pricing."""

from decimal import Decimal

import pytest

from routevalue.domain.models import ElectricityPriceQuote


def test_electricity_price_quote_accepts_precise_price() -> None:
    quote = ElectricityPriceQuote(
        price_per_kilowatt_hour=Decimal("0.31256789"),
    )

    assert quote.price_per_kilowatt_hour == Decimal("0.31256789")


def test_electricity_price_quote_accepts_zero() -> None:
    quote = ElectricityPriceQuote(
        price_per_kilowatt_hour=Decimal(0),
    )

    assert quote.price_per_kilowatt_hour == Decimal(0)


def test_electricity_price_quote_rejects_negative_price() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        ElectricityPriceQuote(
            price_per_kilowatt_hour=Decimal("-0.01"),
        )


@pytest.mark.parametrize(
    "invalid_price",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_electricity_price_quote_rejects_nonfinite_price(
    invalid_price: Decimal,
) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        ElectricityPriceQuote(
            price_per_kilowatt_hour=invalid_price,
        )
