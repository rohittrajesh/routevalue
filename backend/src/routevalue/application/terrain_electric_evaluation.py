"""Terrain-aware BEV energy and electricity-cost evaluation for RouteValue V2."""

from routevalue.application.terrain_electric_consumption import (
    estimate_terrain_electric_consumption,
)
from routevalue.application.terrain_energy import (
    calculate_terrain_gravitational_energy,
)
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
)
from routevalue.domain.models import (
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    EnergyEstimate,
    RouteCandidate,
)


def estimate_terrain_electric_energy_if_available(
    route: RouteCandidate,
    *,
    vehicle: ElectricVehicleSpecification,
    electricity_price_quote: ElectricityPriceQuote | None,
    terrain: NormalizedTerrainProfile | None,
) -> EnergyEstimate | None:
    """Estimate vehicle-specific BEV consumption and monetary energy cost.

    An unavailable electricity price produces no estimate.

    Missing terrain or vehicle mass preserves M5 baseline consumption.
    Gravitational energy is calculated using the selected vehicle's mass,
    preventing accidental reuse of another vehicle's terrain energy.

    Trip-wide terrain coverage policy remains the caller's responsibility.
    """

    if electricity_price_quote is None:
        return None

    if terrain is not None:
        if not isinstance(terrain, NormalizedTerrainProfile):
            raise TypeError("terrain must be a NormalizedTerrainProfile or None")

        if terrain.route_distance_meters != route.distance_meters:
            raise ValueError("terrain distance must match route distance")

    terrain_energy = None

    if terrain is not None and vehicle.vehicle_mass is not None:
        terrain_energy = calculate_terrain_gravitational_energy(
            terrain,
            vehicle_mass=vehicle.vehicle_mass,
        )

    consumption = estimate_terrain_electric_consumption(
        route,
        vehicle=vehicle,
        terrain=terrain_energy,
    )

    electricity_cost = consumption.kilowatt_hours * electricity_price_quote.price_per_kilowatt_hour

    return EnergyEstimate(
        cost=electricity_cost,
        consumption=consumption,
    )
