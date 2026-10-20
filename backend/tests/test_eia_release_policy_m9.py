"""EIA publication cadence fixes the recurring Monday pricing blackout."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from routevalue.domain.fuel_price import is_fuel_price_quote_fresh
from routevalue.domain.models import GasolineGrade
from routevalue.infrastructure.pricing.eia_geography import EIA_CALIFORNIA_REGION
from routevalue.infrastructure.pricing.eia_quote_normalization import normalize_eia_observation
from routevalue.infrastructure.pricing.eia_release_policy import is_eia_weekly_quote_fresh
from routevalue.infrastructure.pricing.eia_xls_models import EiaGasolineObservation


@pytest.mark.parametrize("grade", list(GasolineGrade))
@pytest.mark.parametrize(
    "observation,next_release",
    [
        (date(2026, 10, 12), datetime(2026, 10, 20, 12, tzinfo=ZoneInfo("America/New_York"))),
        (date(2026, 10, 5), datetime(2026, 10, 14, 12, tzinfo=ZoneInfo("America/New_York"))),
        (date(2026, 10, 26), datetime(2026, 11, 3, 12, tzinfo=ZoneInfo("America/New_York"))),
        (date(2026, 12, 28), datetime(2027, 1, 5, 12, tzinfo=ZoneInfo("America/New_York"))),
        (date(2026, 1, 12), datetime(2026, 1, 21, 12, tzinfo=ZoneInfo("America/New_York"))),
        (date(2026, 2, 9), datetime(2026, 2, 18, 12, tzinfo=ZoneInfo("America/New_York"))),
        (date(2026, 5, 18), datetime(2026, 5, 27, 12, tzinfo=ZoneInfo("America/New_York"))),
        (date(2026, 8, 31), datetime(2026, 9, 9, 12, tzinfo=ZoneInfo("America/New_York"))),
        (date(2028, 6, 12), datetime(2028, 6, 21, 12, tzinfo=ZoneInfo("America/New_York"))),
        (date(2028, 12, 18), datetime(2028, 12, 27, 12, tzinfo=ZoneInfo("America/New_York"))),
        (date(2025, 11, 3), datetime(2025, 11, 12, 12, tzinfo=ZoneInfo("America/New_York"))),
        (date(2029, 12, 17), datetime(2029, 12, 26, 12, tzinfo=ZoneInfo("America/New_York"))),
    ],
)
def test_all_grades_survive_until_the_next_publication_window_then_expire(
    grade: GasolineGrade,
    observation: date,
    next_release: datetime,
) -> None:
    quote = normalize_eia_observation(
        observation=EiaGasolineObservation(
            series_id=EIA_CALIFORNIA_REGION.series_for_grade(grade),
            fuel_grade=grade,
            observed_on=observation,
            price_per_gallon=Decimal("4.125"),
        ),
        region=EIA_CALIFORNIA_REGION,
    )
    assert is_eia_weekly_quote_fresh(quote, next_release - timedelta(microseconds=1))
    assert not is_eia_weekly_quote_fresh(quote, next_release)
    assert not is_eia_weekly_quote_fresh(quote, next_release + timedelta(days=7))
    assert quote.observed_at == datetime.combine(observation, datetime.min.time(), tzinfo=UTC)
    assert not is_fuel_price_quote_fresh(quote, as_of=next_release - timedelta(minutes=1))
    assert not is_eia_weekly_quote_fresh(quote, quote.observed_at - timedelta(seconds=1))
    assert quote.market_metadata is not None
    non_eia = replace(quote, market_metadata=replace(quote.market_metadata, provider="Other"))
    assert not is_eia_weekly_quote_fresh(non_eia, next_release - timedelta(minutes=1))
