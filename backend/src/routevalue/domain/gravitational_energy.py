"""Pure gravitational energy calculations for terrain-aware routing."""

from decimal import Decimal

from routevalue.domain.vehicle_mass import VehicleMass

STANDARD_GRAVITY_METERS_PER_SECOND_SQUARED = Decimal("9.80665")
JOULES_PER_KILOWATT_HOUR = Decimal(3600000)


def gravitational_energy_kwh(
    *,
    vehicle_mass: VehicleMass,
    elevation_change_meters: Decimal,
) -> Decimal:
    """Calculate signed gravitational potential-energy change in kWh.

    Positive values indicate climbing; negative values indicate descent.

    This is mechanical energy only. No drivetrain losses, charging
    losses, regenerative recovery, or fuel conversion are included.
    """

    if not isinstance(vehicle_mass, VehicleMass):
        raise TypeError("vehicle_mass must be a VehicleMass")

    if not isinstance(elevation_change_meters, Decimal):
        raise TypeError("elevation_change_meters must be a Decimal")

    if not elevation_change_meters.is_finite():
        raise ValueError("elevation_change_meters must be finite")

    if elevation_change_meters == 0:
        return Decimal(0)

    return (
        vehicle_mass.kilograms
        * STANDARD_GRAVITY_METERS_PER_SECOND_SQUARED
        * elevation_change_meters
        / JOULES_PER_KILOWATT_HOUR
    )
