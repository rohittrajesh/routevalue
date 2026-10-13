"""Pure gasoline consumption correction for gravitational route energy."""

from decimal import Decimal

GASOLINE_KWH_PER_GALLON = Decimal("33.7")
GASOLINE_WHEEL_EFFICIENCY = Decimal("0.25")


def terrain_adjusted_gasoline_gallons(
    *,
    baseline_gallons: Decimal,
    gravitational_kwh: Decimal | None,
    wheel_efficiency: Decimal = GASOLINE_WHEEL_EFFICIENCY,
) -> Decimal:
    """Apply gravitational mechanical energy to segment gasoline consumption.

    The baseline includes ordinary driving losses. Only the additional
    gravitational work is converted into a fuel correction.

    Positive gravitational energy increases fuel consumption.
    Negative gravitational energy reduces propulsion fuel consumption.
    Gasoline cannot regenerate fuel, so consumption is never negative.

    Missing terrain and exact-zero terrain preserve the original baseline.
    """

    if not isinstance(baseline_gallons, Decimal):
        raise TypeError("baseline_gallons must be a Decimal")

    if not baseline_gallons.is_finite() or baseline_gallons < 0:
        raise ValueError("baseline_gallons must be finite and nonnegative")

    if gravitational_kwh is not None:
        if not isinstance(gravitational_kwh, Decimal):
            raise TypeError("gravitational_kwh must be a Decimal or None")

        if not gravitational_kwh.is_finite():
            raise ValueError("gravitational_kwh must be finite")

    if not isinstance(wheel_efficiency, Decimal):
        raise TypeError("wheel_efficiency must be a Decimal")

    if not wheel_efficiency.is_finite() or wheel_efficiency <= 0 or wheel_efficiency > 1:
        raise ValueError("wheel_efficiency must be finite and between 0 and 1")

    if gravitational_kwh is None or gravitational_kwh == 0:
        return baseline_gallons

    fuel_correction = gravitational_kwh / (GASOLINE_KWH_PER_GALLON * wheel_efficiency)

    return max(
        Decimal(0),
        baseline_gallons + fuel_correction,
    )
