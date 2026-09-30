from decimal import Decimal

import httpx
import pytest

from routevalue.api.dependencies import (
    get_google_routes_api_key,
    get_google_routes_http_client,
    get_trip_evaluation_orchestrator,
)
from routevalue.application.models import RouteSearchRequest


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

    with httpx.Client(transport=transport) as client:
        orchestrator = get_trip_evaluation_orchestrator(
            api_key="test-google-routes-key",
            client=client,
        )

        result = orchestrator.evaluate_trip(
            RouteSearchRequest(
                origin="Origin",
                destination="Destination",
            ),
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
        RuntimeError,
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
        RuntimeError,
        match="GOOGLE_ROUTES_API_KEY must be configured",
    ):
        get_google_routes_api_key()


def test_google_routes_http_client_is_closed_after_dependency_finishes() -> None:
    dependency = get_google_routes_http_client()

    client = next(dependency)

    assert not client.is_closed

    dependency.close()

    assert client.is_closed
