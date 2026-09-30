import json
from collections.abc import Generator

import httpx
import pytest
from fastapi.testclient import TestClient

from routevalue.api.dependencies import get_google_routes_http_client
from routevalue.main import app


def test_trip_evaluation_endpoint_uses_google_routes_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        assert request.headers["X-Goog-Api-Key"] == "integration-test-key"

        payload = json.loads(request.content)

        assert payload["origin"] == {
            "address": "Origin",
        }
        assert payload["destination"] == {
            "address": "Destination",
        }

        if request_count == 1:
            assert "routeModifiers" not in payload

            return httpx.Response(
                status_code=200,
                json={
                    "routes": [
                        {
                            "distanceMeters": 10_000,
                            "duration": "900s",
                        }
                    ]
                },
            )

        assert request_count == 2
        assert payload["routeModifiers"] == {
            "avoidTolls": True,
        }

        return httpx.Response(
            status_code=200,
            json={
                "routes": [
                    {
                        "distanceMeters": 10_000,
                        "duration": "900s",
                    },
                    {
                        "distanceMeters": 12_000,
                        "duration": "800s",
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as google_client:

        def override_google_routes_http_client() -> Generator[httpx.Client]:
            yield google_client

        monkeypatch.setenv(
            "GOOGLE_ROUTES_API_KEY",
            "integration-test-key",
        )

        app.dependency_overrides[get_google_routes_http_client] = override_google_routes_http_client

        try:
            with TestClient(app) as client:
                response = client.post(
                    "/trip-evaluations",
                    json={
                        "origin": "Origin",
                        "destination": "Destination",
                        "value_of_time_per_hour": "18.00",
                    },
                )
        finally:
            app.dependency_overrides.clear()

    assert request_count == 2
    assert response.status_code == 200

    assert response.json() == {
        "route_evaluations": [
            {
                "route": {
                    "distance_meters": 10_000,
                    "duration_seconds": 900,
                    "toll_cost": "0",
                },
                "energy_estimate": None,
                "eligibility": {
                    "eligible": False,
                    "reason": "missing_energy_estimate",
                },
            },
            {
                "route": {
                    "distance_meters": 12_000,
                    "duration_seconds": 800,
                    "toll_cost": "0",
                },
                "energy_estimate": None,
                "eligibility": {
                    "eligible": False,
                    "reason": "missing_energy_estimate",
                },
            },
        ],
        "decision": {
            "recommended_route": None,
            "reason": None,
            "numerical_tie": False,
            "missing_data_present": True,
            "candidate_count": 2,
            "eligible_count": 0,
        },
    }
