"""M8 gasoline quote validation regression tests."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
)


def make_quote(
    price: Decimal,
    *,
    grade: GasolineGrade = GasolineGrade.REGULAR,
    source: GasolinePriceSource = GasolinePriceSource.USER_OVERRIDE,
    observed_at: datetime | None = None,
) -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=price,
        fuel_grade=grade,
        source=source,
        observed_at=observed_at,
    )


@pytest.mark.parametrize(
    "price",
    [
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_rejects_nonfinite_gasoline_prices(
    price: Decimal,
) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        make_quote(price)


@pytest.mark.parametrize(
    "price",
    [
        Decimal("-0.01"),
        Decimal(-1),
    ],
)
def test_rejects_negative_gasoline_prices(
    price: Decimal,
) -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        make_quote(price)


def test_accepts_zero_gasoline_price() -> None:
    quote = make_quote(Decimal(0))

    assert quote.price_per_gallon == Decimal(0)


def test_preserves_decimal_precision() -> None:
    quote = make_quote(Decimal("4.759"))

    assert quote.price_per_gallon == Decimal("4.759")


def test_rejects_non_decimal_price() -> None:
    with pytest.raises(TypeError, match="must be a Decimal"):
        make_quote(4.75)  # type: ignore[arg-type]


def test_rejects_invalid_grade() -> None:
    with pytest.raises(TypeError, match="must be a GasolineGrade"):
        make_quote(
            Decimal("4.75"),
            grade="premium",  # type: ignore[arg-type]
        )


def test_rejects_invalid_source() -> None:
    with pytest.raises(TypeError, match="must be a GasolinePriceSource"):
        make_quote(
            Decimal("4.75"),
            source="regional_market",  # type: ignore[arg-type]
        )


def test_market_price_requires_timestamp() -> None:
    with pytest.raises(
        ValueError,
        match="requires an observation timestamp",
    ):
        make_quote(
            Decimal("4.75"),
            source=GasolinePriceSource.REGIONAL_MARKET,
        )


def test_market_price_accepts_aware_timestamp() -> None:
    observed_at = datetime(2026, 10, 12, tzinfo=UTC)

    quote = make_quote(
        Decimal("4.75"),
        source=GasolinePriceSource.REGIONAL_MARKET,
        observed_at=observed_at,
    )

    assert quote.observed_at == observed_at


def test_market_price_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make_quote(
            Decimal("4.75"),
            source=GasolinePriceSource.REGIONAL_MARKET,
            observed_at=datetime(2026, 10, 12, tzinfo=None),  # noqa: DTZ001
        )


def test_user_override_does_not_require_timestamp() -> None:
    quote = make_quote(
        Decimal("5.15"),
        grade=GasolineGrade.PREMIUM,
    )

    assert quote.observed_at is None
    assert quote.fuel_grade is GasolineGrade.PREMIUM
