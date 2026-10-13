"""Fair trip-wide terrain energy evaluation for gasoline and BEV vehicles."""

from collections.abc import Sequence
from dataclasses import dataclass

from routevalue.application.terrain_applicability import (
    TerrainApplicabilityResult,
    evaluate_trip_terrain_applicability,
)
from routevalue.application.terrain_electric_evaluation import (
    estimate_terrain_electric_energy_if_available,
)
from routevalue.application.terrain_gasoline_evaluation import (
    estimate_terrain_gasoline_energy_if_available,
)
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
)
from routevalue.domain.models import (
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    EnergyEstimate,
    GasolinePriceQuote,
    GasolineVehicleSpecification,
    RouteCandidate,
)


@dataclass(frozen=True, slots=True)
class TripTerrainEnergyResult:
    """Energy results computed with one common trip-wide terrain policy."""

    estimates: tuple[EnergyEstimate | None, ...]
    applicability: TerrainApplicabilityResult
    terrain_applied: bool
    missing_vehicle_mass: bool

    @property
    def used_baseline_for_all_routes(self) -> bool:
        return not self.terrain_applied


def evaluate_trip_gasoline_energy(
    routes: Sequence[RouteCandidate],
    *,
    vehicle: GasolineVehicleSpecification,
    fuel_price_quote: GasolinePriceQuote | None,
    terrain_profiles: Sequence[NormalizedTerrainProfile | None],
) -> TripTerrainEnergyResult:
    """Evaluate all gasoline candidates under one consistent terrain policy."""

    applicability = evaluate_trip_terrain_applicability(
        routes,
        terrain_profiles,
    )

    missing_mass = vehicle.vehicle_mass is None
    apply_terrain = applicability.use_terrain and not missing_mass

    estimates = tuple(
        estimate_terrain_gasoline_energy_if_available(
            route,
            vehicle=vehicle,
            fuel_price_quote=fuel_price_quote,
            terrain=profile if apply_terrain else None,
        )
        for route, profile in zip(routes, terrain_profiles, strict=True)
    )

    return TripTerrainEnergyResult(
        estimates=estimates,
        applicability=applicability,
        terrain_applied=apply_terrain,
        missing_vehicle_mass=missing_mass,
    )


def evaluate_trip_electric_energy(
    routes: Sequence[RouteCandidate],
    *,
    vehicle: ElectricVehicleSpecification,
    electricity_price_quote: ElectricityPriceQuote | None,
    terrain_profiles: Sequence[NormalizedTerrainProfile | None],
) -> TripTerrainEnergyResult:
    """Evaluate all BEV candidates under one consistent terrain policy."""

    applicability = evaluate_trip_terrain_applicability(
        routes,
        terrain_profiles,
    )

    missing_mass = vehicle.vehicle_mass is None
    apply_terrain = applicability.use_terrain and not missing_mass

    estimates = tuple(
        estimate_terrain_electric_energy_if_available(
            route,
            vehicle=vehicle,
            electricity_price_quote=electricity_price_quote,
            terrain=profile if apply_terrain else None,
        )
        for route, profile in zip(routes, terrain_profiles, strict=True)
    )

    return TripTerrainEnergyResult(
        estimates=estimates,
        applicability=applicability,
        terrain_applied=apply_terrain,
        missing_vehicle_mass=missing_mass,
    )
