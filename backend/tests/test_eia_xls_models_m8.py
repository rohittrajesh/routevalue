"""M8 typed EIA XLS observation contract tests."""

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from routevalue.domain.models import GasolineGrade
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaGasolineObservation,
    EiaXlsParseError,
    EiaXlsParseFailureReason,
)


def make_observation() -> EiaGasolineObservation:
    return EiaGasolineObservation(
        series_id="EMM_EPMP_PTE_SCA_DPG",
        fuel_grade=GasolineGrade.PREMIUM,
        observed_on=date(2026, 10, 5),
        price_per_gallon=Decimal("6.677"),
    )


def test_valid_observation_preserves_values() -> None:
    observation = make_observation()

    assert observation.series_id == "EMM_EPMP_PTE_SCA_DPG"
    assert observation.fuel_grade is GasolineGrade.PREMIUM
    assert observation.observed_on == date(2026, 10, 5)
    assert observation.price_per_gallon == Decimal("6.677")


def test_observation_preserves_decimal_precision() -> None:
    observation = make_observation()

    assert str(observation.price_per_gallon) == "6.677"


def test_observation_is_immutable() -> None:
    observation = make_observation()

    with pytest.raises(FrozenInstanceError):
        observation.series_id = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    "series_id",
    ["", " ", "\t"],
)
def test_blank_series_is_rejected(series_id: str) -> None:
    with pytest.raises(ValueError, match="cannot be blank"):
        EiaGasolineObservation(
            series_id=series_id,
            fuel_grade=GasolineGrade.REGULAR,
            observed_on=date(2026, 10, 5),
            price_per_gallon=Decimal("4.354"),
        )


def test_invalid_grade_is_rejected() -> None:
    with pytest.raises(TypeError, match="GasolineGrade"):
        EiaGasolineObservation(
            series_id="example",
            fuel_grade="premium",  # type: ignore[arg-type]
            observed_on=date(2026, 10, 5),
            price_per_gallon=Decimal("5.400"),
        )


def test_datetime_is_not_accepted_as_observation_date() -> None:
    with pytest.raises(TypeError, match="must be a date"):
        EiaGasolineObservation(
            series_id="example",
            fuel_grade=GasolineGrade.PREMIUM,
            observed_on=datetime(2026, 10, 5, tzinfo=UTC),
            price_per_gallon=Decimal("5.400"),
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
def test_nonfinite_price_is_rejected(
    price: Decimal,
) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        EiaGasolineObservation(
            series_id="example",
            fuel_grade=GasolineGrade.REGULAR,
            observed_on=date(2026, 10, 5),
            price_per_gallon=price,
        )


def test_negative_price_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        EiaGasolineObservation(
            series_id="example",
            fuel_grade=GasolineGrade.REGULAR,
            observed_on=date(2026, 10, 5),
            price_per_gallon=Decimal("-0.01"),
        )


def test_non_decimal_price_is_rejected() -> None:
    with pytest.raises(TypeError, match="must be a Decimal"):
        EiaGasolineObservation(
            series_id="example",
            fuel_grade=GasolineGrade.REGULAR,
            observed_on=date(2026, 10, 5),
            price_per_gallon=4.354,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "reason",
    list(EiaXlsParseFailureReason),
)
def test_parse_error_preserves_reason(
    reason: EiaXlsParseFailureReason,
) -> None:
    error = EiaXlsParseError(reason)

    assert error.reason is reason
    assert str(error) == reason.value
    assert isinstance(error, ValueError)


def test_parse_error_rejects_invalid_reason() -> None:
    with pytest.raises(
        TypeError,
        match="EiaXlsParseFailureReason",
    ):
        EiaXlsParseError(
            "invalid_workbook"  # type: ignore[arg-type]
        )


def test_observations_compare_deterministically() -> None:
    first = make_observation()
    second = make_observation()

    assert first == second
    assert hash(first) == hash(second)
