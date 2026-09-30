"""Pure route eligibility policy for RouteValue."""

from routevalue.domain.models import (
    DecisionCandidate,
    EligibilityResult,
    EnergyEstimate,
    IneligibilityReason,
    RouteCandidate,
)


def evaluate_route_eligibility(
    route: RouteCandidate,
    *,
    energy_estimate: EnergyEstimate | None,
) -> EligibilityResult:
    """Determine whether a route has the data required for optimization."""

    if route.toll_cost is None:
        return EligibilityResult(
            eligible=False,
            reason=IneligibilityReason.MISSING_TOLL_COST,
        )

    if energy_estimate is None:
        return EligibilityResult(
            eligible=False,
            reason=IneligibilityReason.MISSING_ENERGY_ESTIMATE,
        )

    return EligibilityResult(
        eligible=True,
        reason=None,
    )


def build_decision_candidate_if_eligible(
    route: RouteCandidate,
    *,
    energy_estimate: EnergyEstimate | None,
) -> DecisionCandidate | None:
    """Build a decision candidate only when the route is eligible."""

    eligibility = evaluate_route_eligibility(
        route,
        energy_estimate=energy_estimate,
    )

    if not eligibility.eligible:
        return None

    if energy_estimate is None:
        raise AssertionError("eligible route must have an energy estimate")

    return DecisionCandidate(
        route=route,
        energy_estimate=energy_estimate,
    )
