"""Application orchestration for evaluating RouteValue trips."""

from routevalue.application.models import (
    RouteEvaluation,
    RouteSearchRequest,
    TripEvaluationResult,
)
from routevalue.application.ports import EnergyCostEstimator, RouteProvider
from routevalue.domain.decision_engine import decide_route
from routevalue.domain.eligibility import (
    build_decision_candidate_if_eligible,
    evaluate_route_eligibility,
)
from routevalue.domain.models import DecisionCandidate
from routevalue.domain.units import MoneyPerHour


class TripEvaluationOrchestrator:
    """Coordinate route acquisition, evaluation, and decision-making."""

    def __init__(
        self,
        *,
        route_provider: RouteProvider,
        energy_cost_estimator: EnergyCostEstimator,
    ) -> None:
        self._route_provider = route_provider
        self._energy_cost_estimator = energy_cost_estimator

    def evaluate_trip(
        self,
        request: RouteSearchRequest,
        *,
        value_of_time_per_hour: MoneyPerHour,
    ) -> TripEvaluationResult:
        """Evaluate all candidate routes for one trip."""

        routes = tuple(self._route_provider.get_routes(request))

        route_evaluations: list[RouteEvaluation] = []
        eligible_candidates: list[DecisionCandidate] = []

        for route in routes:
            energy_estimate = self._energy_cost_estimator.estimate_energy(route)

            eligibility = evaluate_route_eligibility(
                route,
                energy_estimate=energy_estimate,
            )

            route_evaluations.append(
                RouteEvaluation(
                    route=route,
                    energy_estimate=energy_estimate,
                    eligibility=eligibility,
                )
            )

            decision_candidate = build_decision_candidate_if_eligible(
                route,
                energy_estimate=energy_estimate,
            )

            if decision_candidate is not None:
                eligible_candidates.append(decision_candidate)

        missing_data_present = any(
            not evaluation.eligibility.eligible for evaluation in route_evaluations
        )

        decision = decide_route(
            eligible_candidates,
            value_of_time_per_hour=value_of_time_per_hour,
            candidate_count=len(routes),
            missing_data_present=missing_data_present,
        )

        return TripEvaluationResult(
            route_evaluations=tuple(route_evaluations),
            decision=decision,
        )
