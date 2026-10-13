"""Electric energy-cost adapter for RouteValue."""

from routevalue.domain.electric_energy import (
    estimate_electric_energy_if_available,
)
from routevalue.domain.models import (
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    EnergyEstimate,
    RouteCandidate,
)


class ElectricEnergyCostEstimator:
    """Estimate baseline electricity cost for normalized routes."""

    def __init__(
        self,
        *,
        vehicle: ElectricVehicleSpecification,
        electricity_price_quote: ElectricityPriceQuote | None,
    ) -> None:
        self._vehicle = vehicle
        self._electricity_price_quote = electricity_price_quote

    def estimate_energy(
        self,
        route: RouteCandidate,
    ) -> EnergyEstimate | None:
        """Return a typed electric energy estimate when pricing is known."""

        return estimate_electric_energy_if_available(
            route,
            vehicle=self._vehicle,
            electricity_price_quote=self._electricity_price_quote,
        )
