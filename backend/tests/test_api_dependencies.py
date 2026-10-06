from decimal import Decimal

import httpx
import pytest

from routevalue.api.dependencies import (
    get_google_routes_api_key,
    get_google_routes_http_client,
    get_trip_evaluation_orchestrator,
)
from routevalue.api.errors import ServiceConfigurationError
from routevalue.api.schemas import (
    GasolineGradeInput,
    GasolineInputs,
    ResolvedLocationInput,
    TripEvaluationRequest,
)
from routevalue.application.models import ResolvedLocation, RouteSearchRequest


def _resolved_location_input(
    display_name: str,
    *,
    source_id: str,
) -> ResolvedLocationInput:
    return ResolvedLocationInput(
        display_name=display_name,
        latitude=32.88,
        longitude=-117.23,
        source="google_places",
        source_id=source_id,
    )


def _route_search_request() -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=ResolvedLocation(
            display_name="Origin",
            latitude=32.88,
            longitude=-117.23,
            source="google_places",
            source_id="origin-place-id",
        ),
        destination=ResolvedLocation(
            display_name="Destination",
            latitude=32.88,
            longitude=-117.23,
            source="google_places",
            source_id="destination-place-id",
        ),
    )


def test_trip_evaluation_dependency_composes_google_route_provider() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        assert request.headers["X-Goog-Api-Key"] == "test-google-routes-key"

        return httpx.Response(
            status_code=200,
            json={},
        )

    transport = httpx.MockTransport(handler)

    api_request = TripEvaluationRequest(
        origin=_resolved_location_input(
            "Origin",
            source_id="origin-place-id",
        ),
        destination=_resolved_location_input(
            "Destination",
            source_id="destination-place-id",
        ),
        value_of_time_per_hour=Decimal("18.00"),
        gasoline=GasolineInputs(
            fuel_efficiency_mpg=Decimal(30),
            fuel_grade=GasolineGradeInput.REGULAR,
            fuel_price_per_gallon=Decimal("4.50"),
        ),
    )

    with httpx.Client(transport=transport) as client:
        orchestrator = get_trip_evaluation_orchestrator(
            request=api_request,
            api_key="test-google-routes-key",
            client=client,
        )

        result = orchestrator.evaluate_trip(
            _route_search_request(),
            value_of_time_per_hour=Decimal("18.00"),
        )

    assert request_count == 2
    assert result.route_evaluations == ()
    assert result.decision.recommended_route is None
    assert result.decision.candidate_count == 0
    assert result.decision.eligible_count == 0
    assert not result.decision.missing_data_present


def test_google_routes_api_key_is_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "GOOGLE_ROUTES_API_KEY",
        "test-google-routes-key",
    )

    api_key = get_google_routes_api_key()

    assert api_key == "test-google-routes-key"


def test_google_routes_api_key_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "GOOGLE_ROUTES_API_KEY",
        raising=False,
    )

    with pytest.raises(
        ServiceConfigurationError,
        match="GOOGLE_ROUTES_API_KEY must be configured",
    ):
        get_google_routes_api_key()


def test_google_routes_api_key_cannot_be_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "GOOGLE_ROUTES_API_KEY",
        "   ",
    )

    with pytest.raises(
        ServiceConfigurationError,
        match="GOOGLE_ROUTES_API_KEY must be configured",
    ):
        get_google_routes_api_key()


def test_google_routes_http_client_is_closed_after_dependency_finishes() -> None:
    dependency = get_google_routes_http_client()

    client = next(dependency)

    assert not client.is_closed

    dependency.close()

    assert client.is_closed
