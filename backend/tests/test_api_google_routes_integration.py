import json
from collections.abc import Generator
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from routevalue.api.dependencies import get_google_routes_http_client
from routevalue.main import app


def _location_payload(
    display_name: str,
    *,
    source_id: str,
) -> dict[str, object]:
    return {
        "display_name": display_name,
        "latitude": 32.88,
        "longitude": -117.23,
        "source": "google_places",
        "source_id": source_id,
    }


def _trip_payload() -> dict[str, object]:
    return {
        "origin": _location_payload(
            "Origin",
            source_id="origin-place-id",
        ),
        "destination": _location_payload(
            "Destination",
            source_id="destination-place-id",
        ),
        "value_of_time_per_hour": "18.00",
        "gasoline": {
            "fuel_efficiency_mpg": "30",
            "fuel_grade": "regular",
            "fuel_price_per_gallon": "4.50",
        },
    }


def test_trip_evaluation_endpoint_uses_google_routes_and_gasoline_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        assert request.headers["X-Goog-Api-Key"] == "integration-test-key"

        payload = json.loads(request.content)

        assert payload["polylineEncoding"] == "GEO_JSON_LINESTRING"
        assert payload["polylineQuality"] == "OVERVIEW"

        assert payload["origin"] == {
            "placeId": "origin-place-id",
        }
        assert payload["destination"] == {
            "placeId": "destination-place-id",
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
                            "polyline": {
                                "geoJsonLinestring": {
                                    "type": "LineString",
                                    "coordinates": [
                                        [-117.2340, 32.8801],
                                        [-117.2200, 32.8200],
                                        [-117.1933, 32.7338],
                                    ],
                                }
                            },
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
                        "polyline": {
                            "geoJsonLinestring": {
                                "type": "LineString",
                                "coordinates": [
                                    [-117.2340, 32.8801],
                                    [-117.2200, 32.8200],
                                    [-117.1933, 32.7338],
                                ],
                            }
                        },
                    },
                    {
                        "distanceMeters": 12_000,
                        "duration": "800s",
                        "polyline": {
                            "geoJsonLinestring": {
                                "type": "LineString",
                                "coordinates": [
                                    [-117.2340, 32.8801],
                                    [-117.2050, 32.7900],
                                    [-117.1933, 32.7338],
                                ],
                            }
                        },
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
                    json=_trip_payload(),
                )
        finally:
            app.dependency_overrides.clear()

    assert request_count == 2
    assert response.status_code == 200

    body = response.json()

    assert len(body["route_evaluations"]) == 2

    first_evaluation = body["route_evaluations"][0]
    second_evaluation = body["route_evaluations"][1]

    assert first_evaluation["route"] == {
        "distance_meters": 10_000,
        "duration_seconds": 900,
        "toll_cost": "0",
    }
    assert second_evaluation["route"] == {
        "distance_meters": 12_000,
        "duration_seconds": 800,
        "toll_cost": "0",
    }

    assert first_evaluation["geometry"] == {
        "points": [
            {
                "latitude": 32.8801,
                "longitude": -117.234,
            },
            {
                "latitude": 32.82,
                "longitude": -117.22,
            },
            {
                "latitude": 32.7338,
                "longitude": -117.1933,
            },
        ]
    }

    assert second_evaluation["geometry"] == {
        "points": [
            {
                "latitude": 32.8801,
                "longitude": -117.234,
            },
            {
                "latitude": 32.79,
                "longitude": -117.205,
            },
            {
                "latitude": 32.7338,
                "longitude": -117.1933,
            },
        ]
    }

    assert first_evaluation["energy_estimate"] is not None
    assert second_evaluation["energy_estimate"] is not None

    first_energy_cost = Decimal(first_evaluation["energy_estimate"]["cost"])
    second_energy_cost = Decimal(second_evaluation["energy_estimate"]["cost"])

    assert first_energy_cost > 0
    assert second_energy_cost > first_energy_cost

    assert first_evaluation["eligibility"] == {
        "eligible": True,
        "reason": None,
    }
    assert second_evaluation["eligibility"] == {
        "eligible": True,
        "reason": None,
    }

    assert body["decision"]["recommended_route"] == second_evaluation["route"]
    assert body["decision"]["reason"] == "faster_route_worth_extra_cost"
    assert body["decision"]["numerical_tie"] is False
    assert body["decision"]["missing_data_present"] is False
    assert body["decision"]["candidate_count"] == 2
    assert body["decision"]["eligible_count"] == 2


def test_trip_evaluation_endpoint_maps_google_http_failure_to_bad_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            status_code=403,
            json={
                "error": {
                    "message": "provider-specific failure",
                }
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
                    json=_trip_payload(),
                )
        finally:
            app.dependency_overrides.clear()

    assert request_count == 1
    assert response.status_code == 502
    assert response.json() == {
        "detail": "routing provider request failed",
    }


def test_trip_evaluation_endpoint_maps_invalid_google_response_to_bad_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            status_code=200,
            content=b"not-json",
            headers={
                "Content-Type": "application/json",
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
                    json=_trip_payload(),
                )
        finally:
            app.dependency_overrides.clear()

    assert request_count == 1
    assert response.status_code == 502
    assert response.json() == {
        "detail": "routing provider returned an invalid response",
    }


def test_trip_evaluation_endpoint_maps_google_server_failure_to_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            status_code=503,
            json={},
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
                    json=_trip_payload(),
                )
        finally:
            app.dependency_overrides.clear()

    assert request_count == 3
    assert response.status_code == 503
    assert response.json() == {
        "detail": "routing provider unavailable",
    }
