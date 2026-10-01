"""Gasoline energy-cost adapter for RouteValue."""

from routevalue.domain.gasoline_energy import (
    estimate_gasoline_energy_if_available,
)
from routevalue.domain.models import (
    EnergyEstimate,
    FuelPriceQuote,
    GasolineVehicleProfile,
    RouteCandidate,
)


class GasolineEnergyCostEstimator:
    """Estimate route gasoline cost using configured V1 gasoline context."""

    def __init__(
        self,
        *,
        vehicle: GasolineVehicleProfile,
        fuel_price_quote: FuelPriceQuote | None,
    ) -> None:
        self._vehicle = vehicle
        self._fuel_price_quote = fuel_price_quote

    def estimate_energy(
        self,
        route: RouteCandidate,
    ) -> EnergyEstimate | None:
        """Estimate gasoline cost for one normalized route."""

        return estimate_gasoline_energy_if_available(
            route,
            vehicle=self._vehicle,
            fuel_price_quote=self._fuel_price_quote,
        )
