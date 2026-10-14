"""M8 deterministic gasoline quote-selection tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from routevalue.application.gasoline_price_failures import (
    GasolinePriceUnavailableError,
    GasolinePriceUnavailableReason,
)
from routevalue.application.gasoline_price_selection import (
    select_gasoline_price_quote,
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

AS_OF = datetime(2026, 10, 13, 12, tzinfo=UTC)


def make_geography(
    region_id: str = "test-region",
) -> GasolinePriceGeography:
    return GasolinePriceGeography(
        scope=GasolinePriceGeographicScope.REGION,
        region_id=region_id,
        display_name=region_id,
    )


def make_market_quote(
    *,
    grade: GasolineGrade = GasolineGrade.PREMIUM,
    geography: GasolinePriceGeography | None = None,
    age_days: int = 1,
    source: GasolinePriceSource = GasolinePriceSource.REGIONAL_MARKET,
) -> GasolinePriceQuote:
    actual_geography = geography or make_geography()

    return GasolinePriceQuote(
        price_per_gallon=Decimal("4.759"),
        fuel_grade=grade,
        source=source,
        observed_at=AS_OF - timedelta(days=age_days),
        market_metadata=GasolineMarketMetadata(
            provider="EIA",
            geography=actual_geography,
        ),
    )


def make_override(
    grade: GasolineGrade = GasolineGrade.PREMIUM,
) -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal("5.25"),
        fuel_grade=grade,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )


def select(
    *,
    grade: GasolineGrade = GasolineGrade.PREMIUM,
    geography: GasolinePriceGeography | None = None,
    override: GasolinePriceQuote | None = None,
    market: GasolinePriceQuote | None = None,
) -> GasolinePriceQuote:
    return select_gasoline_price_quote(
        fuel_grade=grade,
        geography=geography or make_geography(),
        as_of=AS_OF,
        user_override=override,
        market_quote=market,
    )


def test_matching_manual_override_wins() -> None:
    override = make_override()
    market = make_market_quote()

    assert select(override=override, market=market) is override


def test_manual_override_works_without_market_quote() -> None:
    override = make_override()

    assert select(override=override) is override


def test_manual_override_wins_over_stale_market_quote() -> None:
    override = make_override()
    stale = make_market_quote(age_days=8)

    assert select(override=override, market=stale) is override


def test_manual_override_wins_over_mismatched_market_quote() -> None:
    override = make_override()
    market = make_market_quote(grade=GasolineGrade.REGULAR)

    assert select(override=override, market=market) is override


def test_manual_override_rejects_wrong_grade() -> None:
    with pytest.raises(GasolinePriceUnavailableError) as error:
        select(
            override=make_override(GasolineGrade.REGULAR),
        )

    assert error.value.reason is GasolinePriceUnavailableReason.GRADE_MISMATCH


def test_matching_market_quote_is_selected() -> None:
    market = make_market_quote()

    assert select(market=market) is market


def test_missing_market_quote_is_explicit() -> None:
    with pytest.raises(GasolinePriceUnavailableError) as error:
        select()

    assert error.value.reason is GasolinePriceUnavailableReason.PRICE_NOT_FOUND


def test_market_grade_mismatch_is_rejected() -> None:
    market = make_market_quote(grade=GasolineGrade.REGULAR)

    with pytest.raises(GasolinePriceUnavailableError) as error:
        select(market=market)

    assert error.value.reason is GasolinePriceUnavailableReason.GRADE_MISMATCH


def test_market_geography_mismatch_is_rejected() -> None:
    market = make_market_quote(
        geography=make_geography("other-region"),
    )

    with pytest.raises(GasolinePriceUnavailableError) as error:
        select(market=market)

    assert error.value.reason is GasolinePriceUnavailableReason.GEOGRAPHY_MISMATCH


def test_stale_regional_quote_is_rejected() -> None:
    market = make_market_quote(age_days=8)

    with pytest.raises(GasolinePriceUnavailableError) as error:
        select(market=market)

    assert error.value.reason is GasolinePriceUnavailableReason.PRICE_STALE


def test_seven_day_regional_quote_is_accepted() -> None:
    market = make_market_quote(age_days=7)

    assert select(market=market) is market


def test_quote_without_market_metadata_is_rejected() -> None:
    market = GasolinePriceQuote(
        price_per_gallon=Decimal("4.75"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=GasolinePriceSource.REGIONAL_MARKET,
        observed_at=AS_OF,
    )

    with pytest.raises(GasolinePriceUnavailableError) as error:
        select(market=market)

    assert error.value.reason is GasolinePriceUnavailableReason.INVALID_QUOTE


def test_user_override_misrepresented_as_market_is_rejected() -> None:
    with pytest.raises(GasolinePriceUnavailableError) as error:
        select(market=make_override())

    assert error.value.reason is GasolinePriceUnavailableReason.INVALID_QUOTE


def test_selection_is_deterministic() -> None:
    market = make_market_quote()

    first = select(market=market)
    second = select(market=market)

    assert first == second
    assert first is market
    assert second is market


def test_future_market_observation_is_rejected() -> None:
    market = make_market_quote(age_days=-1)

    with pytest.raises(GasolinePriceUnavailableError) as error:
        select(market=market)

    assert error.value.reason is GasolinePriceUnavailableReason.PRICE_STALE


def test_invalid_evaluation_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        select_gasoline_price_quote(
            fuel_grade=GasolineGrade.PREMIUM,
            geography=make_geography(),
            as_of=datetime(2026, 10, 13, tzinfo=None),  # noqa: DTZ001
            market_quote=make_market_quote(),
        )


def test_invalid_market_quote_type_is_rejected() -> None:
    with pytest.raises(GasolinePriceUnavailableError) as error:
        select_gasoline_price_quote(
            fuel_grade=GasolineGrade.PREMIUM,
            geography=make_geography(),
            as_of=AS_OF,
            market_quote="invalid",  # type: ignore[arg-type]
        )

    assert error.value.reason is GasolinePriceUnavailableReason.INVALID_QUOTE
