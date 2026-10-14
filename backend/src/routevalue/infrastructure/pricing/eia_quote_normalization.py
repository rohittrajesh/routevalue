"""Normalize verified EIA XLS observations into domain gasoline quotes.

The parser preserves source observation dates. This adapter applies a
documented conservative UTC timestamp convention and attaches verified
EIA geographic provenance.

No network access, freshness evaluation, or fallback selection occurs here.
"""

from datetime import UTC, datetime, time

from routevalue.domain.gasoline_price_metadata import (
    GasolineMarketMetadata,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaGasolineObservation,
)

EIA_PROVIDER_NAME = "EIA"


def normalize_eia_observation(
    *,
    observation: EiaGasolineObservation,
    region: EiaGasolineRegion,
) -> GasolinePriceQuote:
    """Create a domain quote from one verified EIA observation.

    The source date is represented as midnight UTC at the beginning
    of that date. This is a conservative freshness convention,
    not an actual survey timestamp.

    Publication time is unknown unless independently verified.
    """

    if not isinstance(observation, EiaGasolineObservation):
        raise TypeError("observation must be an EiaGasolineObservation")

    if not isinstance(region, EiaGasolineRegion):
        raise TypeError("region must be an EiaGasolineRegion")

    expected_series = region.series_for_grade(observation.fuel_grade)

    if observation.series_id != expected_series:
        raise ValueError("observation series does not match verified EIA region and grade")

    observed_at = datetime.combine(
        observation.observed_on,
        time.min,
        tzinfo=UTC,
    )

    metadata = GasolineMarketMetadata(
        provider=EIA_PROVIDER_NAME,
        geography=region.geography,
        published_at=None,
    )

    return GasolinePriceQuote(
        price_per_gallon=observation.price_per_gallon,
        fuel_grade=observation.fuel_grade,
        source=GasolinePriceSource.REGIONAL_MARKET,
        observed_at=observed_at,
        market_metadata=metadata,
    )


def normalize_eia_observations(
    *,
    observations: tuple[EiaGasolineObservation, ...],
    region: EiaGasolineRegion,
) -> tuple[GasolinePriceQuote, ...]:
    """Normalize exactly one observation for every gasoline grade.

    Reject missing or repeated grades rather than returning an
    incomplete or ambiguous market-pricing snapshot.
    """

    if not isinstance(observations, tuple):
        raise TypeError("observations must be a tuple")

    if not isinstance(region, EiaGasolineRegion):
        raise TypeError("region must be an EiaGasolineRegion")

    by_grade: dict[GasolineGrade, GasolinePriceQuote] = {}

    for observation in observations:
        quote = normalize_eia_observation(
            observation=observation,
            region=region,
        )

        if quote.fuel_grade in by_grade:
            raise ValueError("duplicate EIA gasoline grade")

        by_grade[quote.fuel_grade] = quote

    if set(by_grade) != set(GasolineGrade):
        raise ValueError("incomplete EIA gasoline grade coverage")

    return tuple(by_grade[grade] for grade in GasolineGrade)
