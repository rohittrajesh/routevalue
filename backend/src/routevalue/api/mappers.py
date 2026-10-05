"""Mappings between HTTP schemas and RouteValue application models."""

from routevalue.api.schemas import (
    CostBreakdownResponse,
    DecisionResponse,
    EligibilityResponse,
    EnergyEstimateResponse,
    GasolineGradeInput,
    ResolvedLocationInput,
    RouteEvaluationResponse,
    RouteResponse,
    TripEvaluationRequest,
    TripEvaluationResponse,
)
from routevalue.application.models import (
    ResolvedLocation,
    RouteSearchRequest,
    TripEvaluationResult,
)
from routevalue.domain.models import (
    CostBreakdown,
    DecisionResult,
    EligibilityResult,
    EnergyEstimate,
    FuelPriceQuote,
    FuelPriceSource,
    GasolineGrade,
    GasolineVehicleProfile,
    RouteCandidate,
)
from routevalue.domain.units import MoneyPerHour


def to_route_search_request(
    request: TripEvaluationRequest,
) -> RouteSearchRequest:
    """Convert an HTTP trip request into an application route-search request."""

    return RouteSearchRequest(
        origin=_to_resolved_location(request.origin),
        destination=_to_resolved_location(request.destination),
    )


def get_value_of_time_per_hour(
    request: TripEvaluationRequest,
) -> MoneyPerHour:
    """Extract the application value-of-time input from an HTTP trip request."""

    return request.value_of_time_per_hour


def _to_gasoline_grade(
    fuel_grade: GasolineGradeInput,
) -> GasolineGrade:
    """Map the public gasoline-grade value into the domain model."""

    grade_mapping = {
        GasolineGradeInput.REGULAR: GasolineGrade.REGULAR,
        GasolineGradeInput.MIDGRADE: GasolineGrade.MIDGRADE,
        GasolineGradeInput.PREMIUM: GasolineGrade.PREMIUM,
    }

    return grade_mapping[fuel_grade]


def to_gasoline_vehicle_profile(
    request: TripEvaluationRequest,
) -> GasolineVehicleProfile:
    """Build the domain gasoline vehicle profile from an HTTP request."""

    return GasolineVehicleProfile(
        fuel_efficiency_mpg=request.gasoline.fuel_efficiency_mpg,
        fuel_grade=_to_gasoline_grade(request.gasoline.fuel_grade),
    )


def to_user_override_fuel_price_quote(
    request: TripEvaluationRequest,
) -> FuelPriceQuote:
    """Build the user-supplied V1 fuel-price quote from an HTTP request."""

    return FuelPriceQuote(
        price_per_gallon=request.gasoline.fuel_price_per_gallon,
        fuel_grade=_to_gasoline_grade(request.gasoline.fuel_grade),
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )


def _to_route_response(route: RouteCandidate) -> RouteResponse:
    """Convert a domain route into its public API representation."""

    return RouteResponse(
        distance_meters=route.distance_meters,
        duration_seconds=route.duration_seconds,
        toll_cost=route.toll_cost,
    )


def _to_energy_estimate_response(
    estimate: EnergyEstimate,
) -> EnergyEstimateResponse:
    """Convert a domain energy estimate into its public API representation."""

    return EnergyEstimateResponse(
        cost=estimate.cost,
    )


def _to_cost_breakdown_response(
    breakdown: CostBreakdown,
) -> CostBreakdownResponse:
    """Convert a domain cost breakdown into its public API representation."""

    return CostBreakdownResponse(
        monetary_cost=breakdown.monetary_cost,
        time_cost=breakdown.time_cost,
        generalized_cost=breakdown.generalized_cost,
    )


def _to_eligibility_response(
    eligibility: EligibilityResult,
) -> EligibilityResponse:
    """Convert a domain eligibility result into its public API representation."""

    return EligibilityResponse(
        eligible=eligibility.eligible,
        reason=eligibility.reason.value if eligibility.reason is not None else None,
    )


def _to_decision_response(
    decision: DecisionResult,
) -> DecisionResponse:
    """Convert a domain decision result into its public API representation."""

    recommended_route = (
        _to_route_response(decision.recommended_route)
        if decision.recommended_route is not None
        else None
    )

    return DecisionResponse(
        recommended_route=recommended_route,
        reason=decision.reason.value if decision.reason is not None else None,
        numerical_tie=decision.numerical_tie,
        missing_data_present=decision.missing_data_present,
        candidate_count=decision.candidate_count,
        eligible_count=decision.eligible_count,
    )


def to_trip_evaluation_response(
    result: TripEvaluationResult,
) -> TripEvaluationResponse:
    """Convert an application trip result into the public API response."""

    route_evaluations = [
        RouteEvaluationResponse(
            route=_to_route_response(evaluation.route),
            energy_estimate=(
                _to_energy_estimate_response(evaluation.energy_estimate)
                if evaluation.energy_estimate is not None
                else None
            ),
            eligibility=_to_eligibility_response(evaluation.eligibility),
            cost_breakdown=(
                _to_cost_breakdown_response(evaluation.cost_breakdown)
                if evaluation.cost_breakdown is not None
                else None
            ),
        )
        for evaluation in result.route_evaluations
    ]

    return TripEvaluationResponse(
        route_evaluations=route_evaluations,
        decision=_to_decision_response(result.decision),
    )


def _to_resolved_location(
    location: ResolvedLocationInput,
) -> ResolvedLocation:
    """Convert an API location into the provider-neutral application model."""

    return ResolvedLocation(
        display_name=location.display_name,
        latitude=location.latitude,
        longitude=location.longitude,
        source=location.source,
        source_id=location.source_id,
    )
