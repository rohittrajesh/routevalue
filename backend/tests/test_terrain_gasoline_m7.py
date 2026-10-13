"""M7-D1 tests for pure terrain-aware gasoline correction."""

from decimal import Decimal

import pytest

from routevalue.domain.terrain_gasoline import (
    GASOLINE_KWH_PER_GALLON,
    GASOLINE_WHEEL_EFFICIENCY,
    terrain_adjusted_gasoline_gallons,
)


def _adjust(
    baseline: str = "1",
    energy: str | None = "0",
    *,
    efficiency: str = "0.25",
) -> Decimal:
    return terrain_adjusted_gasoline_gallons(
        baseline_gallons=Decimal(baseline),
        gravitational_kwh=Decimal(energy) if energy is not None else None,
        wheel_efficiency=Decimal(efficiency),
    )


def test_calibration_constants_are_explicit() -> None:
    assert GASOLINE_KWH_PER_GALLON == Decimal("33.7")
    assert GASOLINE_WHEEL_EFFICIENCY == Decimal("0.25")


def test_flat_terrain_preserves_exact_baseline() -> None:
    baseline = Decimal("0.123456789123456789123456789")

    result = terrain_adjusted_gasoline_gallons(
        baseline_gallons=baseline,
        gravitational_kwh=Decimal(0),
    )

    assert result == baseline


def test_missing_terrain_preserves_exact_baseline() -> None:
    assert _adjust("1.23456789", None) == Decimal("1.23456789")


def test_uphill_increases_gasoline_consumption() -> None:
    assert _adjust("1", "0.8425") == Decimal("1.1")


def test_downhill_reduces_gasoline_consumption() -> None:
    assert _adjust("1", "-0.8425") == Decimal("0.9")


def test_excessive_descent_cannot_create_negative_fuel() -> None:
    assert _adjust("0.1", "-100") == 0


def test_zero_baseline_with_uphill_requires_positive_fuel() -> None:
    assert _adjust("0", "0.8425") == Decimal("0.1")


def test_zero_baseline_and_zero_terrain_remain_zero() -> None:
    assert _adjust("0", "0") == 0


def test_greater_uphill_energy_requires_more_fuel() -> None:
    gentle = _adjust("1", "0.5")
    steep = _adjust("1", "1")

    assert steep > gentle > Decimal(1)


def test_greater_downhill_energy_reduces_fuel_until_zero() -> None:
    gentle = _adjust("1", "-0.5")
    steep = _adjust("1", "-1")

    assert Decimal(0) <= steep < gentle < Decimal(1)


def test_lower_efficiency_requires_more_uphill_fuel() -> None:
    lower = _adjust("1", "1", efficiency="0.20")
    higher = _adjust("1", "1", efficiency="0.30")

    assert lower > higher


@pytest.mark.parametrize(
    "value",
    [
        Decimal(-1),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_invalid_baseline_is_rejected(value: Decimal) -> None:
    with pytest.raises(ValueError):
        terrain_adjusted_gasoline_gallons(
            baseline_gallons=value,
            gravitational_kwh=Decimal(0),
        )


@pytest.mark.parametrize(
    "value",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_nonfinite_gravitational_energy_is_rejected(
    value: Decimal,
) -> None:
    with pytest.raises(ValueError):
        terrain_adjusted_gasoline_gallons(
            baseline_gallons=Decimal(1),
            gravitational_kwh=value,
        )


@pytest.mark.parametrize(
    "efficiency",
    ["0", "-0.1", "1.01", "NaN", "Infinity"],
)
def test_invalid_efficiency_is_rejected(
    efficiency: str,
) -> None:
    with pytest.raises(ValueError):
        _adjust(efficiency=efficiency)


def test_one_hundred_percent_efficiency_is_valid() -> None:
    result = _adjust(
        "1",
        "3.37",
        efficiency="1",
    )

    assert result == Decimal("1.1")


def test_correction_is_deterministic() -> None:
    first = _adjust("1.2345", "0.789")
    second = _adjust("1.2345", "0.789")

    assert first == second


def test_correction_is_independent_of_fuel_price() -> None:
    result = _adjust("1", "0.8425")

    cheap_cost = result * Decimal("3.50")
    expensive_cost = result * Decimal("5.50")

    assert result == Decimal("1.1")
    assert expensive_cost > cheap_cost
