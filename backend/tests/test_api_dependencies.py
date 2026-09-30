from decimal import Decimal

from routevalue.api.dependencies import get_trip_evaluation_orchestrator
from routevalue.application.models import RouteSearchRequest


def test_default_trip_evaluation_dependency_builds_working_orchestrator() -> None:
    orchestrator = get_trip_evaluation_orchestrator()

    result = orchestrator.evaluate_trip(
        RouteSearchRequest(
            origin="Origin",
            destination="Destination",
        ),
        value_of_time_per_hour=Decimal("18.00"),
    )

    assert result.route_evaluations == ()
    assert result.decision.recommended_route is None
    assert result.decision.candidate_count == 0
    assert result.decision.eligible_count == 0
    assert not result.decision.missing_data_present
