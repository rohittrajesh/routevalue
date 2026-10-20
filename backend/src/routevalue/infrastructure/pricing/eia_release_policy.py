"""V2 EIA weekly publication-aware validity; V1 policy is unchanged.

Since April 2025 EIA publishes Monday observations Tuesday around 10 a.m.
Eastern, or Wednesday after a Monday federal holiday. Allow a bounded two-hour
publication/refresh window, then reject the previous week's observation.

Sources (verified October 19, 2026):
https://www.eia.gov/petroleum/gasdiesel/notice.php
https://www.eia.gov/petroleum/gasdiesel/schedule.php

This is an expiry policy, not an inferred publication/observation timestamp.
Refreshing an old workbook never resets observation age.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from routevalue.domain.fuel_price import is_fuel_price_quote_fresh
from routevalue.domain.models import GasolinePriceQuote, GasolinePriceSource

_EASTERN = ZoneInfo("America/New_York")
_PUBLICATION_CUTOFF = time(12)  # 10 a.m. scheduled release + two-hour delivery window.


def _is_release_holiday(day: date) -> bool:
    """Recurring federal holidays affecting Monday collection/Tuesday release."""
    if day.weekday() == 1:
        return (day.month, day.day) in {(1, 1), (6, 19), (7, 4), (11, 11), (12, 25)}
    if day.weekday() != 0:
        return False
    if (day.month, day.day) in {
        (1, 1),
        (1, 2),
        (6, 19),
        (6, 20),
        (7, 4),
        (7, 5),
        (11, 11),
        (11, 12),
        (12, 25),
        (12, 26),
    }:
        return True
    return (
        (day.month in (1, 2) and 15 <= day.day <= 21)
        or (day.month == 5 and day.day >= 25)
        or (day.month == 9 and day.day <= 7)
        or (day.month == 10 and 8 <= day.day <= 14)
    )


def is_eia_weekly_quote_fresh(quote: GasolinePriceQuote, as_of: datetime) -> bool:
    """Accept a normalized EIA Monday quote only until its next release window.

    Other providers and timestamps retain the existing default freshness rule.
    Future observations and data older than ten days are always rejected.
    """
    default_fresh = is_fuel_price_quote_fresh(quote, as_of=as_of)
    metadata = quote.market_metadata
    observed = quote.observed_at
    if (
        quote.source is not GasolinePriceSource.REGIONAL_MARKET
        or metadata is None
        or metadata.provider != "EIA"
        or observed is None
    ):
        return default_fresh
    observed_utc = observed.astimezone(UTC)
    if observed_utc.weekday() != 0 or observed_utc.time() != time.min:
        return default_fresh
    age = as_of - observed
    if age < timedelta(0) or age > timedelta(days=10):
        return False
    next_observation = observed_utc.date() + timedelta(days=7)
    next_tuesday = next_observation + timedelta(days=1)
    release_day = next_observation + timedelta(
        days=2 if _is_release_holiday(next_observation) or _is_release_holiday(next_tuesday) else 1
    )
    expires = datetime.combine(release_day, _PUBLICATION_CUTOFF, tzinfo=_EASTERN)
    return as_of < expires


def latest_expected_eia_observation(as_of: datetime) -> date:
    """Expected Monday observation after the existing holiday-aware 10 a.m. release.

    This schedules acquisition; it never fabricates a source date or extends the
    resolver's noon freshness deadline. Unpublished data remains unusable.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("publication clock must be timezone aware")
    local = as_of.astimezone(_EASTERN)
    monday = local.date() - timedelta(days=local.weekday())
    tuesday = monday + timedelta(days=1)
    release_day = monday + timedelta(
        days=2 if _is_release_holiday(monday) or _is_release_holiday(tuesday) else 1
    )
    release = datetime.combine(release_day, time(10), tzinfo=_EASTERN)
    return monday if local >= release else monday - timedelta(days=7)
