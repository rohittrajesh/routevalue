"""Network-free regression tests for selectable Google route geometry quality."""

import json
from typing import cast

import httpx
import pytest

from routevalue.application.models import (
    ResolvedLocation,
    RouteSearchRequest,
)
from routevalue.infrastructure.routing.google_routes import (
    GooglePolylineQuality,
    GoogleRoutesRouteProvider,
    build_google_routes_request_payload,
)


def _request() -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=ResolvedLocation(
            display_name="Origin",
            latitude=32.88,
            longitude=-117.23,
        ),
        destination=ResolvedLocation(
            display_name="Destination",
            latitude=33.68,
            longitude=-117.82,
        ),
    )


def _response() -> dict[str, object]:
    return {
        "routes": [
            {
                "distanceMeters": 1000,
                "duration": "120s",
                "polyline": {
                    "geoJsonLinestring": {
                        "type": "LineString",
                        "coordinates": [
                            [-117.23, 32.88],
                            [-117.50, 33.25],
                            [-117.82, 33.68],
                        ],
                    }
                },
            }
        ]
    }


@pytest.mark.parametrize(
    ("quality", "expected"),
    [
        ("OVERVIEW", "OVERVIEW"),
        ("HIGH_QUALITY", "HIGH_QUALITY"),
    ],
)
def test_request_payload_respects_explicit_quality(
    quality: GooglePolylineQuality,
    expected: str,
) -> None:
    payload = build_google_routes_request_payload(
        _request(),
        polyline_quality=quality,
    )

    assert payload["polylineQuality"] == expected
    assert payload["polylineEncoding"] == "GEO_JSON_LINESTRING"
    assert payload["travelMode"] == "DRIVE"


def test_default_payload_remains_overview() -> None:
    payload = build_google_routes_request_payload(_request())

    assert payload["polylineQuality"] == "OVERVIEW"


@pytest.mark.parametrize(
    "quality",
    [
        "OVERVIEW",
        "HIGH_QUALITY",
    ],
)
def test_provider_uses_consistent_quality_for_both_route_requests(
    quality: GooglePolylineQuality,
) -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/directions/v2:computeRoutes"

        payload: object = json.loads(request.content)
        assert isinstance(payload, dict)

        requests.append(payload)

        return httpx.Response(200, json=_response())

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as client:
        provider = GoogleRoutesRouteProvider(
            api_key="test-key",
            client=client,
            polyline_quality=quality,
        )

        routes = provider.get_routes(_request())

    assert len(requests) == 2
    assert requests[0]["polylineQuality"] == quality
    assert requests[1]["polylineQuality"] == quality

    assert "routeModifiers" not in requests[0]
    assert requests[1]["routeModifiers"] == {"avoidTolls": True}

    assert len(routes) == 1
    assert routes[0].route.distance_meters == 1000
    assert routes[0].route.duration_seconds == 120

    geometry = routes[0].geometry
    assert geometry is not None
    assert len(geometry.points) == 3
    assert geometry.points[0].latitude == 32.88


def test_provider_defaults_to_overview_geometry() -> None:
    observed_quality: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload: object = json.loads(request.content)
        assert isinstance(payload, dict)

        quality = payload.get("polylineQuality")
        assert isinstance(quality, str)

        observed_quality.append(quality)
        return httpx.Response(200, json=_response())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = GoogleRoutesRouteProvider(
            api_key="test-key",
            client=client,
        )
        provider.get_routes(_request())

    assert observed_quality == ["OVERVIEW", "OVERVIEW"]


def test_invalid_polyline_quality_is_rejected() -> None:
    invalid = cast(GooglePolylineQuality, "UNSUPPORTED")

    with httpx.Client() as client, pytest.raises(ValueError, match="polyline_quality"):
        GoogleRoutesRouteProvider(
            api_key="test-key",
            client=client,
            polyline_quality=invalid,
        )


def test_invalid_request_quality_is_rejected() -> None:
    invalid = cast(GooglePolylineQuality, "UNSUPPORTED")

    with pytest.raises(ValueError, match="polyline_quality"):
        build_google_routes_request_payload(
            _request(),
            polyline_quality=invalid,
        )
