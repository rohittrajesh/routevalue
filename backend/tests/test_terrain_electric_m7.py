"""M7-E1 tests for pure BEV gravitational corrections and regeneration."""

from decimal import Decimal

import pytest

from routevalue.domain.terrain_electric import (
    ELECTRIC_CHARGING_EFFICIENCY,
    ELECTRIC_DRIVE_EFFICIENCY,
    ELECTRIC_REGEN_EFFICIENCY,
    terrain_adjusted_electric_kwh,
)


def _adjust(
    baseline: str = "2",
    energy: str | None = "0",
    *,
    charge: str = "0.84",
    drive: str = "0.75",
    regen: str = "0.65",
) -> Decimal:
    return terrain_adjusted_electric_kwh(
        baseline_kwh=Decimal(baseline),
        gravitational_kwh=(Decimal(energy) if energy is not None else None),
        charging_efficiency=Decimal(charge),
        drive_efficiency=Decimal(drive),
        regen_efficiency=Decimal(regen),
    )


def test_calibration_constants_are_explicit() -> None:
    assert ELECTRIC_CHARGING_EFFICIENCY == Decimal("0.84")
    assert ELECTRIC_DRIVE_EFFICIENCY == Decimal("0.75")
    assert ELECTRIC_REGEN_EFFICIENCY == Decimal("0.65")


def test_flat_terrain_preserves_exact_baseline() -> None:
    baseline = Decimal("1.123456789123456789123456789")

    result = terrain_adjusted_electric_kwh(
        baseline_kwh=baseline,
        gravitational_kwh=Decimal(0),
    )

    assert result == baseline


def test_missing_terrain_preserves_exact_baseline() -> None:
    assert _adjust("1.23456789", None) == Decimal("1.23456789")


def test_uphill_increases_electricity_consumption() -> None:
    adjusted = _adjust("2", "1")

    expected = Decimal(2) + Decimal(1) / (Decimal("0.84") * Decimal("0.75"))

    assert adjusted == expected
    assert adjusted > 2


def test_downhill_recovers_electricity() -> None:
    adjusted = _adjust("2", "-1")

    expected = Decimal(2) - (Decimal("0.65") / Decimal("0.84"))

    assert adjusted == expected
    assert Decimal(0) < adjusted < Decimal(2)


def test_uphill_and_downhill_are_asymmetric() -> None:
    baseline = Decimal(2)

    uphill = _adjust("2", "1")
    downhill = _adjust("2", "-1")

    uphill_penalty = uphill - baseline
    downhill_recovery = baseline - downhill

    assert uphill_penalty > downhill_recovery


def test_extreme_descent_cannot_create_negative_consumption() -> None:
    assert _adjust("0.1", "-100") == 0


def test_zero_baseline_uphill_requires_energy() -> None:
    assert _adjust("0", "0.63") == Decimal(1)


def test_zero_baseline_downhill_remains_zero() -> None:
    assert _adjust("0", "-1") == 0


def test_higher_gravity_increases_uphill_consumption() -> None:
    gentle = _adjust("2", "0.5")
    steep = _adjust("2", "1")

    assert steep > gentle > Decimal(2)


def test_stronger_regen_reduces_downhill_consumption() -> None:
    weak = _adjust("2", "-1", regen="0.4")
    strong = _adjust("2", "-1", regen="0.8")

    assert strong < weak


def test_lower_drive_efficiency_increases_uphill_energy() -> None:
    inefficient = _adjust("2", "1", drive="0.5")
    efficient = _adjust("2", "1", drive="0.9")

    assert inefficient > efficient


def test_lower_charging_efficiency_increases_uphill_energy() -> None:
    inefficient = _adjust("2", "1", charge="0.7")
    efficient = _adjust("2", "1", charge="0.9")

    assert inefficient > efficient


@pytest.mark.parametrize(
    "value",
    ["-1", "NaN", "Infinity", "-Infinity"],
)
def test_invalid_baseline_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        _adjust(baseline=value)


@pytest.mark.parametrize(
    "value",
    ["NaN", "Infinity", "-Infinity"],
)
def test_nonfinite_gravitational_energy_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        _adjust(energy=value)


@pytest.mark.parametrize(
    "name",
    ["charge", "drive", "regen"],
)
@pytest.mark.parametrize(
    "value",
    ["0", "-0.1", "1.1", "NaN", "Infinity"],
)
def test_invalid_efficiencies_are_rejected(
    name: str,
    value: str,
) -> None:
    kwargs = {
        "charge": "0.84",
        "drive": "0.75",
        "regen": "0.65",
    }
    kwargs[name] = value

    with pytest.raises(ValueError):
        _adjust(**kwargs)


def test_one_hundred_percent_efficiencies_are_valid() -> None:
    adjusted = _adjust(
        "2",
        "1",
        charge="1",
        drive="1",
        regen="1",
    )

    assert adjusted == Decimal(3)


def test_regen_does_not_exceed_mechanical_input() -> None:
    baseline = Decimal(5)
    gravitational = Decimal(-1)

    adjusted = terrain_adjusted_electric_kwh(
        baseline_kwh=baseline,
        gravitational_kwh=gravitational,
    )

    recovered_wall_equivalent = baseline - adjusted
    recovered_battery_energy = recovered_wall_equivalent * ELECTRIC_CHARGING_EFFICIENCY

    assert recovered_battery_energy <= abs(gravitational)


def test_deterministic_calculation() -> None:
    first = _adjust("2.123456", "-0.6789")
    second = _adjust("2.123456", "-0.6789")

    assert first == second
