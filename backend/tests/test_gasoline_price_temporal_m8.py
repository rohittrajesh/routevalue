"""M8 gasoline price observation and publication consistency tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from routevalue.domain.fuel_price import (
    is_fuel_price_quote_fresh,
)
from routevalue.domain.gasoline_price_metadata import (
    GasolineMarketMetadata,
    GasolinePriceGeographicScope,
    GasolinePriceGeography,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
)

OBSERVED_AT = datetime(2026, 10, 5, 12, tzinfo=UTC)


def make_quote(
    *,
    observed_at: datetime = OBSERVED_AT,
    published_at: datetime | None = None,
) -> GasolinePriceQuote:
    metadata = GasolineMarketMetadata(
        provider="EIA",
        geography=GasolinePriceGeography(
            scope=GasolinePriceGeographicScope.REGION,
            region_id="test-region",
            display_name="Test Region",
        ),
        published_at=published_at,
    )

    return GasolinePriceQuote(
        price_per_gallon=Decimal("4.759"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=GasolinePriceSource.REGIONAL_MARKET,
        observed_at=observed_at,
        market_metadata=metadata,
    )


def test_publication_after_observation_is_valid() -> None:
    published_at = OBSERVED_AT + timedelta(days=1)

    quote = make_quote(published_at=published_at)

    assert quote.observed_at == OBSERVED_AT
    assert quote.market_metadata is not None
    assert quote.market_metadata.published_at == published_at


def test_publication_equal_to_observation_is_valid() -> None:
    quote = make_quote(published_at=OBSERVED_AT)

    assert quote.market_metadata is not None
    assert quote.market_metadata.published_at == OBSERVED_AT


def test_publication_before_observation_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="publication timestamp cannot precede",
    ):
        make_quote(
            published_at=OBSERVED_AT - timedelta(seconds=1),
        )


def test_unknown_publication_timestamp_is_accepted() -> None:
    quote = make_quote(published_at=None)

    assert quote.market_metadata is not None
    assert quote.market_metadata.published_at is None


def test_publication_does_not_refresh_stale_observation() -> None:
    quote = make_quote(
        published_at=OBSERVED_AT + timedelta(days=8),
    )

    assert not is_fuel_price_quote_fresh(
        quote,
        as_of=OBSERVED_AT + timedelta(days=8),
    )


def test_regional_quote_is_fresh_at_seven_days() -> None:
    quote = make_quote(
        published_at=OBSERVED_AT + timedelta(days=1),
    )

    assert is_fuel_price_quote_fresh(
        quote,
        as_of=OBSERVED_AT + timedelta(days=7),
    )


def test_regional_quote_expires_after_seven_days() -> None:
    quote = make_quote(
        published_at=OBSERVED_AT + timedelta(days=1),
    )

    assert not is_fuel_price_quote_fresh(
        quote,
        as_of=OBSERVED_AT + timedelta(days=7, seconds=1),
    )


def test_future_observation_is_not_fresh() -> None:
    quote = make_quote()

    assert not is_fuel_price_quote_fresh(
        quote,
        as_of=OBSERVED_AT - timedelta(seconds=1),
    )


def test_freshness_ignores_later_publication_time() -> None:
    quote = make_quote(
        published_at=OBSERVED_AT + timedelta(days=6),
    )

    assert is_fuel_price_quote_fresh(
        quote,
        as_of=OBSERVED_AT + timedelta(days=6),
    )

    assert not is_fuel_price_quote_fresh(
        quote,
        as_of=OBSERVED_AT + timedelta(days=8),
    )
