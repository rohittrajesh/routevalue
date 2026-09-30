"""Pure gasoline energy estimation for RouteValue."""

from routevalue.domain.models import (
    EnergyEstimate,
    FuelPriceQuote,
    GasolineVehicleProfile,
    RouteCandidate,
)
from routevalue.domain.units import meters_to_miles


def estimate_gasoline_energy(
    route: RouteCandidate,
    *,
    vehicle: GasolineVehicleProfile,
    fuel_price_quote: FuelPriceQuote,
) -> EnergyEstimate:
    """Estimate route gasoline cost using distance, MPG, and resolved fuel price."""

    if fuel_price_quote.fuel_grade is not vehicle.fuel_grade:
        raise ValueError("fuel price grade must match vehicle fuel grade")

    distance_miles = meters_to_miles(route.distance_meters)
    gallons_used = distance_miles / vehicle.fuel_efficiency_mpg
    fuel_cost = gallons_used * fuel_price_quote.price_per_gallon

    return EnergyEstimate(cost=fuel_cost)


def estimate_gasoline_energy_if_available(
    route: RouteCandidate,
    *,
    vehicle: GasolineVehicleProfile,
    fuel_price_quote: FuelPriceQuote | None,
) -> EnergyEstimate | None:
    """Estimate gasoline cost when the required fuel price is available."""

    if fuel_price_quote is None:
        return None

    return estimate_gasoline_energy(
        route,
        vehicle=vehicle,
        fuel_price_quote=fuel_price_quote,
    )
