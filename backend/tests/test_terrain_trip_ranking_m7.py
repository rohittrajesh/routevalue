"""M7-F3 tests for trip-wide terrain fairness and route ranking."""

from decimal import Decimal

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import ElevationSample, TerrainProfile
from routevalue.application.terrain_applicability import (
    TerrainApplicabilityReason,
    evaluate_trip_terrain_applicability,
)
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
    normalize_terrain_profile,
)
from routevalue.application.terrain_trip_energy import (
    TripTerrainEnergyResult,
    evaluate_trip_electric_energy,
    evaluate_trip_gasoline_energy,
)
from routevalue.domain.decision_engine import (
    GENERALIZED_COST_TIE_TOLERANCE,
    calculate_generalized_cost,
    decide_route,
)
from routevalue.domain.models import (
    DecisionCandidate,
    DecisionResult,
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource


def _route(
    *,
    distance: int = 10_000,
    duration: int = 600,
    toll: str = "0",
) -> RouteCandidate:
    return RouteCandidate(
        distance_meters=distance,
        duration_seconds=duration,
        toll_cost=Decimal(toll),
    )


def _profile(
    elevations: tuple[str | None, ...],
    *,
    distance: int = 10_000,
) -> NormalizedTerrainProfile:
    if len(elevations) < 2:
        raise ValueError("at least two elevations are required")

    return normalize_terrain_profile(
        TerrainProfile(
            route_distance_meters=distance,
            samples=tuple(
                ElevationSample(
                    point=RoutePoint(latitude=32.0, longitude=-117.0),
                    distance_meters=(distance * index // (len(elevations) - 1)),
                    elevation_meters=(Decimal(value) if value is not None else None),
                )
                for index, value in enumerate(elevations)
            ),
        )
    )


def _uphill() -> NormalizedTerrainProfile:
    return _profile(("100", "300", "500", "700", "900", "1100"))


def _downhill() -> NormalizedTerrainProfile:
    return _profile(("1100", "900", "700", "500", "300", "100"))


def _partial() -> NormalizedTerrainProfile:
    # Five 2,000m intervals: three known, two unknown = 60%.
    return _profile(("100", "300", "500", "700", None, None))


def _mass() -> VehicleMass:
    return VehicleMass(
        kilograms=Decimal(2000),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
    )


def _gas_vehicle(
    *,
    with_mass: bool = True,
) -> GasolineVehicleSpecification:
    return GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
        vehicle_mass=_mass() if with_mass else None,
    )


def _electric_vehicle(
    *,
    with_mass: bool = True,
) -> ElectricVehicleSpecification:
    return ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.30"),
        vehicle_mass=_mass() if with_mass else None,
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


def _decide(
    routes: tuple[RouteCandidate, ...],
    evaluation: TripTerrainEnergyResult,
) -> DecisionResult:
    """Pass the shared energy estimates through the existing decision engine."""

    candidates = tuple(
        DecisionCandidate(route=route, energy_estimate=estimate)
        for route, estimate in zip(routes, evaluation.estimates, strict=True)
        if estimate is not None and route.toll_cost is not None
    )

    return decide_route(
        candidates,
        value_of_time_per_hour=Decimal(0),
        candidate_count=len(routes),
        missing_data_present=(
            any(estimate is None for estimate in evaluation.estimates)
            or any(route.toll_cost is None for route in routes)
        ),
    )


def test_original_tie_tolerance_is_unchanged() -> None:
    assert GENERALIZED_COST_TIE_TOLERANCE == Decimal("0.10")


def test_gasoline_ranking_changes_when_terrain_is_applied() -> None:
    routes = (
        _route(duration=600),
        _route(duration=700),
    )

    with_terrain = evaluate_trip_gasoline_energy(
        routes,
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        terrain_profiles=(_uphill(), _downhill()),
    )

    without_terrain = evaluate_trip_gasoline_energy(
        routes,
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        terrain_profiles=(None, None),
    )

    assert with_terrain.terrain_applied
    assert not without_terrain.terrain_applied

    terrain_decision = _decide(routes, with_terrain)
    baseline_decision = _decide(routes, without_terrain)

    assert terrain_decision.recommended_route == routes[1]
    assert baseline_decision.recommended_route == routes[0]


def test_electric_ranking_changes_when_terrain_is_applied() -> None:
    routes = (
        _route(duration=600),
        _route(duration=700),
    )

    with_terrain = evaluate_trip_electric_energy(
        routes,
        vehicle=_electric_vehicle(),
        electricity_price_quote=_electric_quote(),
        terrain_profiles=(_uphill(), _downhill()),
    )

    without_terrain = evaluate_trip_electric_energy(
        routes,
        vehicle=_electric_vehicle(),
        electricity_price_quote=_electric_quote(),
        terrain_profiles=(None, None),
    )

    assert with_terrain.terrain_applied
    assert not without_terrain.terrain_applied

    assert _decide(routes, with_terrain).recommended_route == routes[1]
    assert _decide(routes, without_terrain).recommended_route == routes[0]


def test_one_low_coverage_candidate_restores_gasoline_baseline_ranking() -> None:
    routes = (
        _route(duration=600),
        _route(duration=700),
        _route(duration=800, toll="20"),
    )

    result = evaluate_trip_gasoline_energy(
        routes,
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        terrain_profiles=(_uphill(), _downhill(), _partial()),
    )

    assert not result.terrain_applied
    assert result.applicability.blocking_candidate_indices == (2,)
    assert result.applicability.reason is (TerrainApplicabilityReason.INSUFFICIENT_COVERAGE)

    assert _decide(routes, result).recommended_route == routes[0]


def test_one_low_coverage_candidate_restores_electric_baseline_ranking() -> None:
    routes = (
        _route(duration=600),
        _route(duration=700),
        _route(duration=800, toll="20"),
    )

    result = evaluate_trip_electric_energy(
        routes,
        vehicle=_electric_vehicle(),
        electricity_price_quote=_electric_quote(),
        terrain_profiles=(_uphill(), _downhill(), _partial()),
    )

    assert not result.terrain_applied
    assert result.applicability.blocking_candidate_indices == (2,)
    assert _decide(routes, result).recommended_route == routes[0]


def test_missing_mass_disables_terrain_without_removing_candidates() -> None:
    routes = (
        _route(duration=600),
        _route(duration=700),
    )

    evaluation = evaluate_trip_electric_energy(
        routes,
        vehicle=_electric_vehicle(with_mass=False),
        electricity_price_quote=_electric_quote(),
        terrain_profiles=(_uphill(), _downhill()),
    )

    decision = _decide(routes, evaluation)

    assert evaluation.applicability.use_terrain
    assert not evaluation.terrain_applied
    assert evaluation.missing_vehicle_mass
    assert decision.eligible_count == 2
    assert decision.recommended_route == routes[0]


def test_gasoline_missing_mass_keeps_all_candidates() -> None:
    routes = (
        _route(duration=600),
        _route(duration=700),
    )

    evaluation = evaluate_trip_gasoline_energy(
        routes,
        vehicle=_gas_vehicle(with_mass=False),
        fuel_price_quote=_gas_quote(),
        terrain_profiles=(_uphill(), _downhill()),
    )

    decision = _decide(routes, evaluation)

    assert not evaluation.terrain_applied
    assert decision.eligible_count == 2
    assert decision.recommended_route == routes[0]


def test_missing_electricity_price_preserves_ineligibility_semantics() -> None:
    routes = (
        _route(duration=600),
        _route(duration=700),
    )

    evaluation = evaluate_trip_electric_energy(
        routes,
        vehicle=_electric_vehicle(),
        electricity_price_quote=None,
        terrain_profiles=(_uphill(), _downhill()),
    )

    decision = _decide(routes, evaluation)

    assert evaluation.estimates == (None, None)
    assert decision.candidate_count == 2
    assert decision.eligible_count == 0
    assert decision.missing_data_present
    assert decision.recommended_route is None


def test_missing_gasoline_price_preserves_ineligibility_semantics() -> None:
    routes = (
        _route(duration=600),
        _route(duration=700),
    )

    evaluation = evaluate_trip_gasoline_energy(
        routes,
        vehicle=_gas_vehicle(),
        fuel_price_quote=None,
        terrain_profiles=(_uphill(), _downhill()),
    )

    decision = _decide(routes, evaluation)

    assert evaluation.estimates == (None, None)
    assert decision.eligible_count == 0
    assert decision.missing_data_present
    assert decision.recommended_route is None


def test_zero_electricity_price_remains_a_known_estimate() -> None:
    routes = (
        _route(duration=600),
        _route(duration=700),
    )

    evaluation = evaluate_trip_electric_energy(
        routes,
        vehicle=_electric_vehicle(),
        electricity_price_quote=ElectricityPriceQuote(price_per_kilowatt_hour=Decimal(0)),
        terrain_profiles=(_uphill(), _downhill()),
    )

    assert all(estimate is not None and estimate.cost == 0 for estimate in evaluation.estimates)
    assert _decide(routes, evaluation).eligible_count == 2


def test_gasoline_terrain_cost_enters_existing_generalized_cost() -> None:
    routes = (
        _route(duration=600, toll="2"),
        _route(duration=700, toll="0"),
    )

    evaluation = evaluate_trip_gasoline_energy(
        routes,
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        terrain_profiles=(_uphill(), _downhill()),
    )

    first_estimate = evaluation.estimates[0]
    assert first_estimate is not None

    candidate = DecisionCandidate(
        route=routes[0],
        energy_estimate=first_estimate,
    )

    assert calculate_generalized_cost(candidate, Decimal(0)) == first_estimate.cost + Decimal(2)


def test_tie_breaking_still_prefers_faster_route() -> None:
    routes = (
        _route(duration=600),
        _route(duration=700),
    )

    evaluation = evaluate_trip_gasoline_energy(
        routes,
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        terrain_profiles=(None, None),
    )

    decision = _decide(routes, evaluation)

    assert decision.numerical_tie
    assert decision.recommended_route == routes[0]


def test_ranking_is_deterministic() -> None:
    routes = (
        _route(duration=600),
        _route(duration=700),
    )

    evaluation = evaluate_trip_gasoline_energy(
        routes,
        vehicle=_gas_vehicle(),
        fuel_price_quote=_gas_quote(),
        terrain_profiles=(_uphill(), _downhill()),
    )

    assert _decide(routes, evaluation) == _decide(routes, evaluation)


@pytest.mark.parametrize("vehicle_type", ["gasoline", "electric"])
def test_exact_eighty_percent_coverage_is_accepted(
    vehicle_type: str,
) -> None:
    # Four usable 200m intervals + one unknown = exactly 80%.
    exactly_eighty = _profile(
        ("100", "110", "120", "130", "140", None),
        distance=1000,
    )

    route = _route(distance=1000)

    applicability = evaluate_trip_terrain_applicability(
        [route],
        [exactly_eighty],
    )

    assert applicability.candidate_coverages == (Decimal("0.8"),)
    assert applicability.use_terrain

    if vehicle_type == "gasoline":
        result = evaluate_trip_gasoline_energy(
            (route,),
            vehicle=_gas_vehicle(),
            fuel_price_quote=_gas_quote(),
            terrain_profiles=(exactly_eighty,),
        )
    else:
        result = evaluate_trip_electric_energy(
            (route,),
            vehicle=_electric_vehicle(),
            electricity_price_quote=_electric_quote(),
            terrain_profiles=(exactly_eighty,),
        )

    assert result.terrain_applied
    assert result.applicability.blocking_candidate_indices == ()
