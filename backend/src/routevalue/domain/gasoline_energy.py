"""Pure gasoline energy estimation for RouteValue."""

from routevalue.domain.energy_consumption import (
    estimate_baseline_gasoline_consumption,
)
from routevalue.domain.models import (
    EnergyEstimate,
    GasolinePriceQuote,
    GasolineVehicleProfile,
    GasolineVehicleSpecification,
    RouteCandidate,
)


def estimate_gasoline_energy(
    route: RouteCandidate,
    *,
    vehicle: GasolineVehicleProfile,
    fuel_price_quote: GasolinePriceQuote,
) -> EnergyEstimate:
    """Estimate route gasoline consumption and cost using the baseline model."""

    if fuel_price_quote.fuel_grade is not vehicle.fuel_grade:
        raise ValueError("fuel price grade must match vehicle fuel grade")

    specification = GasolineVehicleSpecification(
        combined_mpg=vehicle.fuel_efficiency_mpg,
        fuel_grade=vehicle.fuel_grade,
    )

    consumption = estimate_baseline_gasoline_consumption(
        route,
        vehicle=specification,
    )

    fuel_cost = consumption.gallons * fuel_price_quote.price_per_gallon

    return EnergyEstimate(
        cost=fuel_cost,
        consumption=consumption,
    )


def estimate_gasoline_energy_if_available(
    route: RouteCandidate,
    *,
    vehicle: GasolineVehicleProfile,
    fuel_price_quote: GasolinePriceQuote | None,
) -> EnergyEstimate | None:
    """Estimate gasoline energy when the required fuel price is available."""

    if fuel_price_quote is None:
        return None

    return estimate_gasoline_energy(
        route,
        vehicle=vehicle,
        fuel_price_quote=fuel_price_quote,
    )
