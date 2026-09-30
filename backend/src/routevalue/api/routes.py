"""HTTP routes for the RouteValue API."""

from typing import Annotated

from fastapi import APIRouter, Depends

from routevalue.api.dependencies import get_trip_evaluation_orchestrator
from routevalue.api.mappers import (
    get_value_of_time_per_hour,
    to_route_search_request,
    to_trip_evaluation_response,
)
from routevalue.api.schemas import (
    TripEvaluationRequest,
    TripEvaluationResponse,
)
from routevalue.application.trip_evaluation import TripEvaluationOrchestrator

router = APIRouter()


@router.post(
    "/trip-evaluations",
    response_model=TripEvaluationResponse,
)
def evaluate_trip(
    request: TripEvaluationRequest,
    orchestrator: Annotated[
        TripEvaluationOrchestrator,
        Depends(get_trip_evaluation_orchestrator),
    ],
) -> TripEvaluationResponse:
    """Evaluate candidate routes for one trip."""

    result = orchestrator.evaluate_trip(
        to_route_search_request(request),
        value_of_time_per_hour=get_value_of_time_per_hour(request),
    )

    return to_trip_evaluation_response(result)
