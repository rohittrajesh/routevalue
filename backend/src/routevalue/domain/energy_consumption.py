"""Pure baseline energy-consumption calculations for RouteValue."""

from routevalue.domain.models import (
    ElectricConsumption,
    ElectricVehicleSpecification,
    GasolineConsumption,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.units import meters_to_miles


def estimate_baseline_gasoline_consumption(
    route: RouteCandidate,
    *,
    vehicle: GasolineVehicleSpecification,
) -> GasolineConsumption:
    """Estimate baseline gasoline consumption from route distance and combined MPG."""

    distance_miles = meters_to_miles(route.distance_meters)
    gallons = distance_miles / vehicle.combined_mpg

    return GasolineConsumption(gallons=gallons)


def estimate_baseline_electric_consumption(
    route: RouteCandidate,
    *,
    vehicle: ElectricVehicleSpecification,
) -> ElectricConsumption:
    """Estimate baseline BEV consumption from route distance and combined efficiency."""

    distance_miles = meters_to_miles(route.distance_meters)
    kilowatt_hours = distance_miles * vehicle.combined_kwh_per_mile

    return ElectricConsumption(kilowatt_hours=kilowatt_hours)
