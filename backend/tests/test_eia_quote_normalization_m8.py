"""M8 EIA observation-to-domain quote normalization tests."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceSource,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
)
from routevalue.infrastructure.pricing.eia_quote_normalization import (
    EIA_PROVIDER_NAME,
    normalize_eia_observation,
    normalize_eia_observations,
)
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaGasolineObservation,
)


def make_observation(
    *,
    grade: GasolineGrade = GasolineGrade.REGULAR,
    price: str = "6.227",
    region_id: str = "SCA",
) -> EiaGasolineObservation:
    products = {
        GasolineGrade.REGULAR: "EPMR",
        GasolineGrade.MIDGRADE: "EPMM",
        GasolineGrade.PREMIUM: "EPMP",
    }

    return EiaGasolineObservation(
        series_id=(f"EMM_{products[grade]}_PTE_{region_id}_DPG"),
        fuel_grade=grade,
        observed_on=date(2026, 10, 5),
        price_per_gallon=Decimal(price),
    )


def make_california_observations() -> tuple[EiaGasolineObservation, ...]:
    return (
        make_observation(),
        make_observation(
            grade=GasolineGrade.MIDGRADE,
            price="6.510",
        ),
        make_observation(
            grade=GasolineGrade.PREMIUM,
            price="6.677",
        ),
    )


def test_california_quote_preserves_price_and_grade() -> None:
    quote = normalize_eia_observation(
        observation=make_observation(),
        region=EIA_CALIFORNIA_REGION,
    )

    assert quote.price_per_gallon == Decimal("6.227")
    assert quote.fuel_grade is GasolineGrade.REGULAR
    assert quote.source is GasolinePriceSource.REGIONAL_MARKET


def test_observation_date_uses_conservative_utc_convention() -> None:
    quote = normalize_eia_observation(
        observation=make_observation(),
        region=EIA_CALIFORNIA_REGION,
    )

    assert quote.observed_at == datetime(2026, 10, 5, 0, 0, tzinfo=UTC)


def test_market_metadata_preserves_geography() -> None:
    quote = normalize_eia_observation(
        observation=make_observation(),
        region=EIA_CALIFORNIA_REGION,
    )

    assert quote.market_metadata is not None
    assert quote.market_metadata.provider == EIA_PROVIDER_NAME
    assert quote.market_metadata.geography == EIA_CALIFORNIA_REGION.geography


def test_publication_time_is_not_fabricated() -> None:
    quote = normalize_eia_observation(
        observation=make_observation(),
        region=EIA_CALIFORNIA_REGION,
    )

    assert quote.market_metadata is not None
    assert quote.market_metadata.published_at is None


def test_trailing_decimal_precision_is_preserved() -> None:
    quote = normalize_eia_observation(
        observation=make_observation(
            grade=GasolineGrade.MIDGRADE,
            price="6.510",
        ),
        region=EIA_CALIFORNIA_REGION,
    )

    assert str(quote.price_per_gallon) == "6.510"


def test_national_quote_uses_national_geography() -> None:
    quote = normalize_eia_observation(
        observation=make_observation(
            price="4.354",
            region_id="NUS",
        ),
        region=EIA_US_REGION,
    )

    assert quote.price_per_gallon == Decimal("4.354")
    assert quote.market_metadata is not None
    assert quote.market_metadata.geography == EIA_US_REGION.geography


def test_california_observation_cannot_be_national() -> None:
    with pytest.raises(ValueError, match="series does not match"):
        normalize_eia_observation(
            observation=make_observation(),
            region=EIA_US_REGION,
        )


def test_grade_series_mismatch_is_rejected() -> None:
    observation = EiaGasolineObservation(
        series_id="EMM_EPMR_PTE_SCA_DPG",
        fuel_grade=GasolineGrade.PREMIUM,
        observed_on=date(2026, 10, 5),
        price_per_gallon=Decimal("6.677"),
    )

    with pytest.raises(ValueError, match="series does not match"):
        normalize_eia_observation(
            observation=observation,
            region=EIA_CALIFORNIA_REGION,
        )


def test_invalid_observation_type_is_rejected() -> None:
    with pytest.raises(TypeError, match="EiaGasolineObservation"):
        normalize_eia_observation(
            observation="invalid",  # type: ignore[arg-type]
            region=EIA_CALIFORNIA_REGION,
        )


def test_invalid_region_type_is_rejected() -> None:
    with pytest.raises(TypeError, match="EiaGasolineRegion"):
        normalize_eia_observation(
            observation=make_observation(),
            region="california",  # type: ignore[arg-type]
        )


def test_complete_snapshot_preserves_enum_order() -> None:
    observations = make_california_observations()

    quotes = normalize_eia_observations(
        observations=tuple(reversed(observations)),
        region=EIA_CALIFORNIA_REGION,
    )

    assert [quote.fuel_grade for quote in quotes] == list(GasolineGrade)
    assert [quote.price_per_gallon for quote in quotes] == [
        Decimal("6.227"),
        Decimal("6.510"),
        Decimal("6.677"),
    ]


def test_duplicate_grade_is_rejected() -> None:
    observation = make_observation()

    with pytest.raises(ValueError, match="duplicate EIA gasoline grade"):
        normalize_eia_observations(
            observations=(
                observation,
                observation,
                make_observation(
                    grade=GasolineGrade.PREMIUM,
                    price="6.677",
                ),
            ),
            region=EIA_CALIFORNIA_REGION,
        )


def test_missing_grade_is_rejected() -> None:
    with pytest.raises(ValueError, match="incomplete"):
        normalize_eia_observations(
            observations=(make_observation(),),
            region=EIA_CALIFORNIA_REGION,
        )


def test_empty_snapshot_is_rejected() -> None:
    with pytest.raises(ValueError, match="incomplete"):
        normalize_eia_observations(
            observations=(),
            region=EIA_CALIFORNIA_REGION,
        )


def test_snapshot_is_deterministic() -> None:
    observations = make_california_observations()

    first = normalize_eia_observations(
        observations=observations,
        region=EIA_CALIFORNIA_REGION,
    )
    second = normalize_eia_observations(
        observations=observations,
        region=EIA_CALIFORNIA_REGION,
    )

    assert first == second


def test_snapshot_rejects_non_tuple_input() -> None:
    with pytest.raises(TypeError, match="tuple"):
        normalize_eia_observations(
            observations=[],  # type: ignore[arg-type]
            region=EIA_CALIFORNIA_REGION,
        )


def test_snapshot_rejects_invalid_region() -> None:
    with pytest.raises(TypeError, match="EiaGasolineRegion"):
        normalize_eia_observations(
            observations=(),
            region="unknown",  # type: ignore[arg-type]
        )
