"""Pure BEV energy corrections for gravitational route energy."""

from decimal import Decimal

ELECTRIC_CHARGING_EFFICIENCY = Decimal("0.84")
ELECTRIC_DRIVE_EFFICIENCY = Decimal("0.75")
ELECTRIC_REGEN_EFFICIENCY = Decimal("0.65")


def terrain_adjusted_electric_kwh(
    *,
    baseline_kwh: Decimal,
    gravitational_kwh: Decimal | None,
    charging_efficiency: Decimal = ELECTRIC_CHARGING_EFFICIENCY,
    drive_efficiency: Decimal = ELECTRIC_DRIVE_EFFICIENCY,
    regen_efficiency: Decimal = ELECTRIC_REGEN_EFFICIENCY,
) -> Decimal:
    """Adjust one segment's wall-equivalent electrical energy.

    Uphill gravitational work increases electricity consumption, accounting
    for charging and driving conversion losses.

    Downhill gravitational work may reduce electricity consumption through
    conservative regenerative recovery.

    Missing or flat terrain preserves the baseline exactly.

    Net segment consumption is bounded below by zero. This is a V2
    purchased-energy approximation, not a battery state-of-charge model.
    """

    if not isinstance(baseline_kwh, Decimal):
        raise TypeError("baseline_kwh must be a Decimal")

    if not baseline_kwh.is_finite() or baseline_kwh < 0:
        raise ValueError("baseline_kwh must be finite and nonnegative")

    if gravitational_kwh is not None:
        if not isinstance(gravitational_kwh, Decimal):
            raise TypeError("gravitational_kwh must be a Decimal or None")

        if not gravitational_kwh.is_finite():
            raise ValueError("gravitational_kwh must be finite")

    for name, efficiency in (
        ("charging_efficiency", charging_efficiency),
        ("drive_efficiency", drive_efficiency),
        ("regen_efficiency", regen_efficiency),
    ):
        if not isinstance(efficiency, Decimal):
            raise TypeError(f"{name} must be a Decimal")

        if not efficiency.is_finite() or efficiency <= 0 or efficiency > 1:
            raise ValueError(f"{name} must be finite and between 0 and 1")

    if gravitational_kwh is None or gravitational_kwh == 0:
        return baseline_kwh

    if gravitational_kwh > 0:
        correction = gravitational_kwh / (charging_efficiency * drive_efficiency)
    else:
        correction = gravitational_kwh * regen_efficiency / charging_efficiency

    return max(
        Decimal(0),
        baseline_kwh + correction,
    )
