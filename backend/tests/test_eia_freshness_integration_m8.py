"""Integration tests for normalized EIA quotes and domain freshness."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from routevalue.domain.fuel_price import (
    REGIONAL_MARKET_MAX_AGE,
    is_fuel_price_quote_fresh,
    resolve_fuel_price_quote,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
)
from routevalue.infrastructure.pricing.eia_quote_normalization import (
    normalize_eia_observation,
)
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaGasolineObservation,
)

OBSERVATION_DATE = date(2026, 10, 5)
OBSERVED_AT = datetime(2026, 10, 5, tzinfo=UTC)


def make_eia_quote() -> GasolinePriceQuote:
    observation = EiaGasolineObservation(
        series_id="EMM_EPMP_PTE_SCA_DPG",
        fuel_grade=GasolineGrade.PREMIUM,
        observed_on=OBSERVATION_DATE,
        price_per_gallon=Decimal("6.677"),
    )

    return normalize_eia_observation(
        observation=observation,
        region=EIA_CALIFORNIA_REGION,
    )


def make_manual_quote() -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal("5.999"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )


def test_normalized_quote_uses_regional_source() -> None:
    quote = make_eia_quote()

    assert quote.source is GasolinePriceSource.REGIONAL_MARKET
    assert quote.observed_at == OBSERVED_AT


def test_regional_freshness_limit_remains_seven_days() -> None:
    assert REGIONAL_MARKET_MAX_AGE == timedelta(days=7)


@pytest.mark.parametrize(
    ("as_of", "expected"),
    [
        (datetime(2026, 10, 5, tzinfo=UTC), True),
        (datetime(2026, 10, 11, tzinfo=UTC), True),
        (datetime(2026, 10, 12, tzinfo=UTC), True),
        (datetime(2026, 10, 13, tzinfo=UTC), False),
        (datetime(2026, 10, 14, tzinfo=UTC), False),
    ],
)
def test_real_domain_regional_freshness(
    as_of: datetime,
    expected: bool,
) -> None:
    assert (
        is_fuel_price_quote_fresh(
            make_eia_quote(),
            as_of=as_of,
        )
        is expected
    )


def test_exact_seven_day_boundary_is_fresh() -> None:
    assert is_fuel_price_quote_fresh(
        make_eia_quote(),
        as_of=OBSERVED_AT + timedelta(days=7),
    )


def test_one_second_beyond_boundary_is_stale() -> None:
    assert not is_fuel_price_quote_fresh(
        make_eia_quote(),
        as_of=OBSERVED_AT
        + timedelta(
            days=7,
            seconds=1,
        ),
    )


def test_future_dated_observation_is_not_fresh() -> None:
    assert not is_fuel_price_quote_fresh(
        make_eia_quote(),
        as_of=OBSERVED_AT - timedelta(seconds=1),
    )


def test_stale_eia_quote_is_not_selected() -> None:
    selected = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.PREMIUM,
        as_of=datetime(2026, 10, 13, tzinfo=UTC),
        regional_market_quote=make_eia_quote(),
    )

    assert selected is None


def test_fresh_eia_quote_is_selected() -> None:
    quote = make_eia_quote()

    selected = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.PREMIUM,
        as_of=datetime(2026, 10, 12, tzinfo=UTC),
        regional_market_quote=quote,
    )

    assert selected == quote


def test_manual_override_beats_fresh_eia_quote() -> None:
    manual = make_manual_quote()

    selected = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.PREMIUM,
        as_of=datetime(2026, 10, 12, tzinfo=UTC),
        user_override=manual,
        regional_market_quote=make_eia_quote(),
    )

    assert selected == manual


def test_manual_override_beats_stale_eia_quote() -> None:
    manual = make_manual_quote()

    selected = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.PREMIUM,
        as_of=datetime(2026, 10, 13, tzinfo=UTC),
        user_override=manual,
        regional_market_quote=make_eia_quote(),
    )

    assert selected == manual


def test_manual_override_works_without_market_data() -> None:
    manual = make_manual_quote()

    selected = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.PREMIUM,
        as_of=datetime(2026, 10, 13, tzinfo=UTC),
        user_override=manual,
    )

    assert selected == manual


def test_wrong_fuel_grade_cannot_satisfy_selection() -> None:
    selected = resolve_fuel_price_quote(
        fuel_grade=GasolineGrade.REGULAR,
        as_of=datetime(2026, 10, 12, tzinfo=UTC),
        regional_market_quote=make_eia_quote(),
    )

    assert selected is None
