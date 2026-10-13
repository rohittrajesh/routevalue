"""Provider-neutral V2 trip evaluation with shared terrain policy."""

from collections.abc import Sequence
from dataclasses import dataclass

from routevalue.application.models import (
    ProvidedRoute,
    RouteEvaluation,
    TripEvaluationResult,
)
from routevalue.application.terrain_normalization import (
    NormalizedTerrainProfile,
)
from routevalue.application.terrain_trip_energy import (
    TripTerrainEnergyResult,
    evaluate_trip_electric_energy,
    evaluate_trip_gasoline_energy,
)
from routevalue.domain.decision_engine import (
    calculate_cost_breakdown,
    decide_route,
)
from routevalue.domain.eligibility import (
    build_decision_candidate_if_eligible,
    evaluate_route_eligibility,
)
from routevalue.domain.models import (
    DecisionCandidate,
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    GasolinePriceQuote,
    GasolineVehicleSpecification,
)
from routevalue.domain.units import MoneyPerHour


@dataclass(frozen=True, slots=True)
class TerrainTripEvaluationOutcome:
    """Existing trip decision plus explicit terrain applicability diagnostics."""

    trip: TripEvaluationResult
    terrain_energy: TripTerrainEnergyResult


class TerrainTripEvaluationOrchestrator:
    """Evaluate prepared routes under a single V2 terrain policy.

    The caller acquires routes and prepares normalized terrain.
    This orchestrator makes no external calls and leaves V1 unchanged.
    """

    def evaluate_gasoline_trip(
        self,
        provided_routes: Sequence[ProvidedRoute],
        *,
        terrain_profiles: Sequence[NormalizedTerrainProfile | None],
        vehicle: GasolineVehicleSpecification,
        fuel_price_quote: GasolinePriceQuote | None,
        value_of_time_per_hour: MoneyPerHour,
    ) -> TerrainTripEvaluationOutcome:
        routes = tuple(provided_routes)
        self._validate_inputs(routes, value_of_time_per_hour)

        terrain_energy = evaluate_trip_gasoline_energy(
            tuple(provided.route for provided in routes),
            vehicle=vehicle,
            fuel_price_quote=fuel_price_quote,
            terrain_profiles=terrain_profiles,
        )

        return self._assemble_trip(
            routes,
            terrain_energy,
            value_of_time_per_hour=value_of_time_per_hour,
        )

    def evaluate_electric_trip(
        self,
        provided_routes: Sequence[ProvidedRoute],
        *,
        terrain_profiles: Sequence[NormalizedTerrainProfile | None],
        vehicle: ElectricVehicleSpecification,
        electricity_price_quote: ElectricityPriceQuote | None,
        value_of_time_per_hour: MoneyPerHour,
    ) -> TerrainTripEvaluationOutcome:
        routes = tuple(provided_routes)
        self._validate_inputs(routes, value_of_time_per_hour)

        terrain_energy = evaluate_trip_electric_energy(
            tuple(provided.route for provided in routes),
            vehicle=vehicle,
            electricity_price_quote=electricity_price_quote,
            terrain_profiles=terrain_profiles,
        )

        return self._assemble_trip(
            routes,
            terrain_energy,
            value_of_time_per_hour=value_of_time_per_hour,
        )

    @staticmethod
    def _validate_inputs(
        routes: tuple[ProvidedRoute, ...],
        value_of_time_per_hour: MoneyPerHour,
    ) -> None:
        if not routes:
            raise ValueError("trip must contain at least one route")

        if any(not isinstance(provided, ProvidedRoute) for provided in routes):
            raise TypeError("provided_routes must contain ProvidedRoute")

        if value_of_time_per_hour < 0:
            raise ValueError("value_of_time_per_hour cannot be negative")

    @staticmethod
    def _assemble_trip(
        provided_routes: tuple[ProvidedRoute, ...],
        terrain_energy: TripTerrainEnergyResult,
        *,
        value_of_time_per_hour: MoneyPerHour,
    ) -> TerrainTripEvaluationOutcome:
        if len(provided_routes) != len(terrain_energy.estimates):
            raise ValueError("route and energy estimate counts must match")

        evaluations: list[RouteEvaluation] = []
        eligible_candidates: list[DecisionCandidate] = []

        for provided, energy_estimate in zip(
            provided_routes,
            terrain_energy.estimates,
            strict=True,
        ):
            route = provided.route

            eligibility = evaluate_route_eligibility(
                route,
                energy_estimate=energy_estimate,
            )

            candidate = build_decision_candidate_if_eligible(
                route,
                energy_estimate=energy_estimate,
            )

            cost_breakdown = None

            if candidate is not None:
                cost_breakdown = calculate_cost_breakdown(
                    candidate,
                    value_of_time_per_hour,
                )
                eligible_candidates.append(candidate)

            evaluations.append(
                RouteEvaluation(
                    route=route,
                    energy_estimate=energy_estimate,
                    eligibility=eligibility,
                    cost_breakdown=cost_breakdown,
                    geometry=provided.geometry,
                )
            )

        missing_data_present = any(
            not evaluation.eligibility.eligible for evaluation in evaluations
        )

        decision = decide_route(
            eligible_candidates,
            value_of_time_per_hour=value_of_time_per_hour,
            candidate_count=len(provided_routes),
            missing_data_present=missing_data_present,
        )

        trip = TripEvaluationResult(
            route_evaluations=tuple(evaluations),
            decision=decision,
        )

        return TerrainTripEvaluationOutcome(
            trip=trip,
            terrain_energy=terrain_energy,
        )
