"""M7-G2 tests for provider-neutral V2 trip evaluation."""

from decimal import Decimal

import pytest

from routevalue.application.models import (
    ProvidedRoute,
    RouteGeometry,
    RoutePoint,
)
from routevalue.application.terrain import ElevationSample, TerrainProfile
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
    normalize_terrain_profile,
)
from routevalue.application.terrain_trip_evaluation import (
    TerrainTripEvaluationOrchestrator,
)
from routevalue.domain.decision_engine import calculate_generalized_cost
from routevalue.domain.models import (
    DecisionCandidate,
    DecisionReason,
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
    GasolineVehicleSpecification,
    IneligibilityReason,
    RouteCandidate,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource


def _provided(
    duration: int,
    *,
    toll: Decimal | None = Decimal(0),
) -> ProvidedRoute:
    return ProvidedRoute(
        route=RouteCandidate(
            distance_meters=1000,
            duration_seconds=duration,
            toll_cost=toll,
        ),
        geometry=RouteGeometry(
            points=(
                RoutePoint(32.0, -117.0),
                RoutePoint(32.01, -117.01),
            )
        ),
    )


def _routes() -> tuple[ProvidedRoute, ...]:
    return (_provided(500), _provided(600))


def _terrain(
    elevations: tuple[str | None, ...],
) -> NormalizedTerrainProfile:
    return normalize_terrain_profile(
        TerrainProfile(
            route_distance_meters=1000,
            samples=tuple(
                ElevationSample(
                    point=RoutePoint(32.0, -117.0),
                    distance_meters=1000 * index // (len(elevations) - 1),
                    elevation_meters=(Decimal(value) if value is not None else None),
                )
                for index, value in enumerate(elevations)
            ),
        )
    )


def _uphill() -> NormalizedTerrainProfile:
    return _terrain(("100", "110", "120", "130", "140"))


def _downhill() -> NormalizedTerrainProfile:
    return _terrain(("140", "130", "120", "110", "100"))


def _low_coverage() -> NormalizedTerrainProfile:
    return _terrain(("100", "110", "120", "130", None))


def _mass() -> VehicleMass:
    return VehicleMass(
        kilograms=Decimal(1800),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
    )


def _gas_vehicle(
    *,
    known_mass: bool = True,
) -> GasolineVehicleSpecification:
    return GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
        vehicle_mass=_mass() if known_mass else None,
    )


def _electric_vehicle() -> ElectricVehicleSpecification:
    return ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
        vehicle_mass=_mass(),
    )


def _gas_quote() -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )


def _electric_quote() -> ElectricityPriceQuote:
    return ElectricityPriceQuote(
        price_per_kilowatt_hour=Decimal("0.30"),
    )


def test_gasoline_trip_preserves_route_order_and_geometry() -> None:
    provided = _routes()

    outcome = TerrainTripEvaluationOrchestrator().evaluate_gasoline_trip(
        provided,
        terrain_profiles=(_uphill(), _downhill()),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(20),
    )

    assert outcome.terrain_energy.terrain_applied
    assert len(outcome.trip.route_evaluations) == 2

    for index, evaluation in enumerate(outcome.trip.route_evaluations):
        assert evaluation.route == provided[index].route
        assert evaluation.geometry == provided[index].geometry
        assert evaluation.eligibility.eligible
        assert evaluation.cost_breakdown is not None

    assert outcome.trip.decision.eligible_count == 2
    assert not outcome.trip.decision.missing_data_present


def test_electric_trip_uses_terrain_on_all_candidates() -> None:
    outcome = TerrainTripEvaluationOrchestrator().evaluate_electric_trip(
        _routes(),
        terrain_profiles=(_uphill(), _downhill()),
        vehicle=_electric_vehicle(),
        electricity_price_quote=_electric_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert outcome.terrain_energy.terrain_applied
    assert outcome.trip.decision.eligible_count == 2
    assert all(
        evaluation.energy_estimate is not None for evaluation in outcome.trip.route_evaluations
    )


@pytest.mark.parametrize("kind", ["gasoline", "electric"])
def test_low_coverage_falls_back_for_all_candidates(kind: str) -> None:
    orchestrator = TerrainTripEvaluationOrchestrator()

    if kind == "gasoline":
        outcome = orchestrator.evaluate_gasoline_trip(
            _routes(),
            terrain_profiles=(_uphill(), _low_coverage()),
            vehicle=_gas_vehicle(),
            fuel_price_quote=_gas_quote(),
            value_of_time_per_hour=Decimal(0),
        )
    else:
        outcome = orchestrator.evaluate_electric_trip(
            _routes(),
            terrain_profiles=(_uphill(), _low_coverage()),
            vehicle=_electric_vehicle(),
            electricity_price_quote=_electric_quote(),
            value_of_time_per_hour=Decimal(0),
        )

    assert outcome.terrain_energy.used_baseline_for_all_routes
    assert outcome.terrain_energy.applicability.blocking_candidate_indices == (1,)
    assert outcome.trip.decision.eligible_count == 2
    assert not outcome.trip.decision.missing_data_present


def test_missing_vehicle_mass_uses_baseline() -> None:
    outcome = TerrainTripEvaluationOrchestrator().evaluate_gasoline_trip(
        _routes(),
        terrain_profiles=(_uphill(), _downhill()),
        vehicle=_gas_vehicle(known_mass=False),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert outcome.terrain_energy.missing_vehicle_mass
    assert not outcome.terrain_energy.terrain_applied
    assert outcome.trip.decision.eligible_count == 2


def test_missing_price_keeps_routes_ineligible() -> None:
    outcome = TerrainTripEvaluationOrchestrator().evaluate_electric_trip(
        _routes(),
        terrain_profiles=(_uphill(), _downhill()),
        vehicle=_electric_vehicle(),
        electricity_price_quote=None,
        value_of_time_per_hour=Decimal(0),
    )

    assert outcome.trip.decision.candidate_count == 2
    assert outcome.trip.decision.eligible_count == 0
    assert outcome.trip.decision.missing_data_present
    assert outcome.trip.decision.recommended_route is None

    assert all(
        evaluation.eligibility.reason is IneligibilityReason.MISSING_ENERGY_ESTIMATE
        for evaluation in outcome.trip.route_evaluations
    )


def test_missing_toll_keeps_one_route_ineligible() -> None:
    provided = (_provided(500, toll=None), _provided(600))

    outcome = TerrainTripEvaluationOrchestrator().evaluate_gasoline_trip(
        provided,
        terrain_profiles=(_uphill(), _downhill()),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    first, second = outcome.trip.route_evaluations

    assert first.eligibility.reason is IneligibilityReason.MISSING_TOLL_COST
    assert first.cost_breakdown is None
    assert second.eligibility.eligible
    assert outcome.trip.decision.eligible_count == 1
    assert outcome.trip.decision.missing_data_present
    assert outcome.trip.decision.recommended_route == provided[1].route
    assert outcome.trip.decision.reason is DecisionReason.ONLY_ELIGIBLE_ROUTE


def test_cost_breakdown_matches_existing_decision_engine() -> None:
    outcome = TerrainTripEvaluationOrchestrator().evaluate_gasoline_trip(
        _routes(),
        terrain_profiles=(_uphill(), _downhill()),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(25),
    )

    first = outcome.trip.route_evaluations[0]
    assert first.energy_estimate is not None
    assert first.cost_breakdown is not None

    candidate = DecisionCandidate(
        route=first.route,
        energy_estimate=first.energy_estimate,
    )

    assert first.cost_breakdown.generalized_cost == calculate_generalized_cost(
        candidate,
        Decimal(25),
    )


def test_zero_price_is_known_not_missing() -> None:
    outcome = TerrainTripEvaluationOrchestrator().evaluate_electric_trip(
        _routes(),
        terrain_profiles=(_uphill(), _downhill()),
        vehicle=_electric_vehicle(),
        electricity_price_quote=ElectricityPriceQuote(price_per_kilowatt_hour=Decimal(0)),
        value_of_time_per_hour=Decimal(0),
    )

    assert outcome.trip.decision.eligible_count == 2
    assert not outcome.trip.decision.missing_data_present

    assert all(
        evaluation.energy_estimate is not None and evaluation.energy_estimate.cost == 0
        for evaluation in outcome.trip.route_evaluations
    )


def test_missing_profiles_keep_trip_eligible_with_known_prices() -> None:
    outcome = TerrainTripEvaluationOrchestrator().evaluate_gasoline_trip(
        _routes(),
        terrain_profiles=(None, None),
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(0),
    )

    assert outcome.terrain_energy.used_baseline_for_all_routes
    assert outcome.trip.decision.eligible_count == 2
    assert not outcome.trip.decision.missing_data_present


def test_negative_value_of_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="value_of_time"):
        TerrainTripEvaluationOrchestrator().evaluate_gasoline_trip(
            _routes(),
            terrain_profiles=(_uphill(), _downhill()),
            vehicle=_gas_vehicle(),
            fuel_price_quote=_gas_quote(),
            value_of_time_per_hour=Decimal(-1),
        )


def test_empty_trip_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one route"):
        TerrainTripEvaluationOrchestrator().evaluate_electric_trip(
            (),
            terrain_profiles=(),
            vehicle=_electric_vehicle(),
            electricity_price_quote=_electric_quote(),
            value_of_time_per_hour=Decimal(0),
        )


def test_profile_count_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="same length"):
        TerrainTripEvaluationOrchestrator().evaluate_gasoline_trip(
            _routes(),
            terrain_profiles=(_uphill(),),
            vehicle=_gas_vehicle(),
            fuel_price_quote=_gas_quote(),
            value_of_time_per_hour=Decimal(0),
        )


def test_evaluation_is_deterministic() -> None:
    orchestrator = TerrainTripEvaluationOrchestrator()
    routes = _routes()
    profiles = (_uphill(), _downhill())

    first = orchestrator.evaluate_gasoline_trip(
        routes,
        terrain_profiles=profiles,
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(15),
    )
    second = orchestrator.evaluate_gasoline_trip(
        routes,
        terrain_profiles=profiles,
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        value_of_time_per_hour=Decimal(15),
    )

    assert first == second
