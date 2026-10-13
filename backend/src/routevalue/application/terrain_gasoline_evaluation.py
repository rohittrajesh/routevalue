"""Terrain-aware gasoline energy evaluation for RouteValue V2."""

from routevalue.application.terrain_energy import (
    calculate_terrain_gravitational_energy,
)
from routevalue.application.terrain_gasoline_consumption import (
    estimate_terrain_gasoline_consumption,
)
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
)
from routevalue.domain.models import (
    EnergyEstimate,
    GasolinePriceQuote,
    GasolineVehicleSpecification,
    RouteCandidate,
)


def estimate_terrain_gasoline_energy_if_available(
    route: RouteCandidate,
    *,
    vehicle: GasolineVehicleSpecification,
    fuel_price_quote: GasolinePriceQuote | None,
    terrain: NormalizedTerrainProfile | None,
) -> EnergyEstimate | None:
    """Estimate gasoline cost from a vehicle-specific terrain calculation.

    A missing fuel price produces no estimate, matching M5 semantics.
    Missing mass or terrain preserves the existing baseline calculation.

    No provider-derived gravitational energy can enter this boundary from
    another vehicle: gravitational energy is computed internally using the
    selected vehicle's mass.
    """

    if fuel_price_quote is None:
        return None

    if fuel_price_quote.fuel_grade is not vehicle.fuel_grade:
        raise ValueError("fuel price grade must match vehicle fuel grade")

    terrain_energy = None

    if terrain is not None:
        if not isinstance(terrain, NormalizedTerrainProfile):
            raise TypeError("terrain must be a NormalizedTerrainProfile or None")

        if terrain.route_distance_meters != route.distance_meters:
            raise ValueError("terrain distance must match route distance")

        if vehicle.vehicle_mass is not None:
            terrain_energy = calculate_terrain_gravitational_energy(
                terrain,
                vehicle_mass=vehicle.vehicle_mass,
            )

    consumption = estimate_terrain_gasoline_consumption(
        route,
        vehicle=vehicle,
        terrain=terrain_energy,
    )

    return EnergyEstimate(
        consumption=consumption,
        cost=consumption.gallons * fuel_price_quote.price_per_gallon,
    )
