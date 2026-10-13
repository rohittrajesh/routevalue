"""Pure electricity energy-cost estimation for RouteValue."""

from routevalue.domain.energy_consumption import (
    estimate_baseline_electric_consumption,
)
from routevalue.domain.models import (
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    EnergyEstimate,
    RouteCandidate,
)


def estimate_electric_energy(
    route: RouteCandidate,
    *,
    vehicle: ElectricVehicleSpecification,
    electricity_price_quote: ElectricityPriceQuote,
) -> EnergyEstimate:
    """Estimate baseline BEV consumption and electricity cost.

    Use persisted combined kWh-per-mile efficiency and the supplied
    electricity price. Do not model terrain, charging, or regeneration.
    """

    consumption = estimate_baseline_electric_consumption(
        route,
        vehicle=vehicle,
    )

    electricity_cost = consumption.kilowatt_hours * electricity_price_quote.price_per_kilowatt_hour

    return EnergyEstimate(
        cost=electricity_cost,
        consumption=consumption,
    )


def estimate_electric_energy_if_available(
    route: RouteCandidate,
    *,
    vehicle: ElectricVehicleSpecification,
    electricity_price_quote: ElectricityPriceQuote | None,
) -> EnergyEstimate | None:
    """Estimate electric energy when a price quote is available.

    A missing quote produces no energy estimate. A known zero
    electricity price remains valid.
    """

    if electricity_price_quote is None:
        return None

    return estimate_electric_energy(
        route,
        vehicle=vehicle,
        electricity_price_quote=electricity_price_quote,
    )
