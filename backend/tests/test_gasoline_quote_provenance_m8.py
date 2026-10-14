"""M8 gasoline quote provenance and compatibility tests."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from routevalue.domain.gasoline_price_metadata import (
    GasolineMarketMetadata,
    GasolinePriceGeographicScope,
    GasolinePriceGeography,
)
from routevalue.domain.models import (
    FuelPriceQuote,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
)

OBSERVED_AT = datetime(2026, 10, 12, tzinfo=UTC)


def make_metadata(
    scope: GasolinePriceGeographicScope,
) -> GasolineMarketMetadata:
    return GasolineMarketMetadata(
        provider="EIA",
        geography=GasolinePriceGeography(
            scope=scope,
            region_id="example-region",
            display_name="Example Region",
        ),
        published_at=OBSERVED_AT,
    )


def make_market_quote(
    source: GasolinePriceSource,
    metadata: GasolineMarketMetadata | None,
) -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal("4.759"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=source,
        observed_at=OBSERVED_AT,
        market_metadata=metadata,
    )


def test_existing_four_argument_quote_remains_valid() -> None:
    quote = GasolinePriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    assert quote.market_metadata is None


def test_existing_market_quote_without_metadata_remains_valid() -> None:
    quote = GasolinePriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=GasolinePriceSource.REGIONAL_MARKET,
        observed_at=OBSERVED_AT,
    )

    assert quote.market_metadata is None


def test_quote_preserves_market_provenance() -> None:
    metadata = make_metadata(GasolinePriceGeographicScope.REGION)

    quote = make_market_quote(
        GasolinePriceSource.REGIONAL_MARKET,
        metadata,
    )

    assert quote.market_metadata is metadata
    assert quote.price_per_gallon == Decimal("4.759")
    assert quote.fuel_grade is GasolineGrade.PREMIUM


@pytest.mark.parametrize(
    "scope",
    [
        GasolinePriceGeographicScope.NATIONAL,
        GasolinePriceGeographicScope.REGION,
        GasolinePriceGeographicScope.STATE,
        GasolinePriceGeographicScope.METRO,
    ],
)
def test_regional_quote_accepts_supported_scopes(
    scope: GasolinePriceGeographicScope,
) -> None:
    quote = make_market_quote(
        GasolinePriceSource.REGIONAL_MARKET,
        make_metadata(scope),
    )

    assert quote.market_metadata is not None
    assert quote.market_metadata.geography.scope is scope


@pytest.mark.parametrize(
    "scope",
    [
        GasolinePriceGeographicScope.METRO,
        GasolinePriceGeographicScope.STATION,
    ],
)
def test_local_quote_accepts_supported_scopes(
    scope: GasolinePriceGeographicScope,
) -> None:
    quote = make_market_quote(
        GasolinePriceSource.LOCAL_MARKET,
        make_metadata(scope),
    )

    assert quote.market_metadata is not None
    assert quote.market_metadata.geography.scope is scope


def test_regional_quote_rejects_station_scope() -> None:
    with pytest.raises(ValueError, match="incompatible geographic scope"):
        make_market_quote(
            GasolinePriceSource.REGIONAL_MARKET,
            make_metadata(GasolinePriceGeographicScope.STATION),
        )


def test_local_quote_rejects_national_scope() -> None:
    with pytest.raises(ValueError, match="incompatible geographic scope"):
        make_market_quote(
            GasolinePriceSource.LOCAL_MARKET,
            make_metadata(GasolinePriceGeographicScope.NATIONAL),
        )


def test_user_override_rejects_market_metadata() -> None:
    with pytest.raises(ValueError, match="user override"):
        GasolinePriceQuote(
            price_per_gallon=Decimal("4.75"),
            fuel_grade=GasolineGrade.REGULAR,
            source=GasolinePriceSource.USER_OVERRIDE,
            observed_at=None,
            market_metadata=make_metadata(GasolinePriceGeographicScope.REGION),
        )


def test_invalid_metadata_type_is_rejected() -> None:
    with pytest.raises(TypeError, match="GasolineMarketMetadata"):
        GasolinePriceQuote(
            price_per_gallon=Decimal("4.75"),
            fuel_grade=GasolineGrade.REGULAR,
            source=GasolinePriceSource.REGIONAL_MARKET,
            observed_at=OBSERVED_AT,
            market_metadata="EIA",  # type: ignore[arg-type]
        )


def test_legacy_quote_alias_remains_intact() -> None:
    assert FuelPriceQuote is GasolinePriceQuote


def test_observation_and_publication_times_remain_distinct() -> None:
    publication = datetime(2026, 10, 13, tzinfo=UTC)

    metadata = GasolineMarketMetadata(
        provider="EIA",
        geography=GasolinePriceGeography(
            scope=GasolinePriceGeographicScope.REGION,
            region_id="example-region",
            display_name="Example Region",
        ),
        published_at=publication,
    )

    quote = make_market_quote(
        GasolinePriceSource.REGIONAL_MARKET,
        metadata,
    )

    assert quote.observed_at == OBSERVED_AT
    assert quote.market_metadata is not None
    assert quote.market_metadata.published_at == publication
    assert quote.observed_at != quote.market_metadata.published_at
