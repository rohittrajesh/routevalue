"""Application-layer models for RouteValue use cases."""

from dataclasses import dataclass

from routevalue.domain.models import (
    DecisionResult,
    EligibilityResult,
    EnergyEstimate,
    RouteCandidate,
)


@dataclass(frozen=True, slots=True)
class RouteSearchRequest:
    """Provider-neutral request for candidate routes between two locations."""

    origin: str
    destination: str

    def __post_init__(self) -> None:
        if not self.origin.strip():
            raise ValueError("origin cannot be blank")

        if not self.destination.strip():
            raise ValueError("destination cannot be blank")


@dataclass(frozen=True, slots=True)
class RouteEvaluation:
    """Application-level evaluation details for one candidate route."""

    route: RouteCandidate
    energy_estimate: EnergyEstimate | None
    eligibility: EligibilityResult


@dataclass(frozen=True, slots=True)
class TripEvaluationResult:
    """Complete application-level result for evaluating one trip."""

    route_evaluations: tuple[RouteEvaluation, ...]
    decision: DecisionResult

    def __post_init__(self) -> None:
        if len(self.route_evaluations) != self.decision.candidate_count:
            raise ValueError("route evaluation count must match decision candidate count")

        eligible_count = sum(
            evaluation.eligibility.eligible for evaluation in self.route_evaluations
        )

        if eligible_count != self.decision.eligible_count:
            raise ValueError("eligible route evaluation count must match decision eligible count")

        missing_data_present = any(
            not evaluation.eligibility.eligible for evaluation in self.route_evaluations
        )
        if missing_data_present != self.decision.missing_data_present:
            raise ValueError("route evaluation missing-data state must match decision")
