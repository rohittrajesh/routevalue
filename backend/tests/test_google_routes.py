import json
from decimal import Decimal

import httpx
import pytest

from routevalue.application.models import RouteSearchRequest
from routevalue.application.ports import RouteProvider
from routevalue.domain.models import RouteCandidate
from routevalue.infrastructure.routing.google_routes import (
    GOOGLE_ROUTES_COMPUTE_URL,
    GOOGLE_ROUTES_FIELD_MASK,
    GoogleRoutesHTTPError,
    GoogleRoutesResponseError,
    GoogleRoutesRouteProvider,
    GoogleRoutesTransportError,
    build_google_routes_request_payload,
    parse_google_routes_response,
)


def test_parse_google_routes_response_returns_empty_tuple_when_no_routes() -> None:
    routes = parse_google_routes_response({})

    assert routes == ()


def test_parse_google_routes_response_preserves_google_route_order() -> None:
    payload = {
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
    }

    routes = parse_google_routes_response(payload)

    assert routes == (
        RouteCandidate(
            distance_meters=10_000,
            duration_seconds=900,
            toll_cost=Decimal(0),
        ),
        RouteCandidate(
            distance_meters=12_000,
            duration_seconds=800,
            toll_cost=Decimal(0),
        ),
    )


def test_parse_google_routes_response_maps_absent_toll_info_to_zero() -> None:
    payload = {
        "routes": [
            {
                "distanceMeters": 10_000,
                "duration": "900s",
                "travelAdvisory": {},
            }
        ]
    }

    routes = parse_google_routes_response(payload)

    assert routes[0].toll_cost == Decimal(0)


def test_parse_google_routes_response_maps_known_usd_toll_exactly() -> None:
    payload = {
        "routes": [
            {
                "distanceMeters": 10_000,
                "duration": "900s",
                "travelAdvisory": {
                    "tollInfo": {
                        "estimatedPrice": [
                            {
                                "currencyCode": "USD",
                                "units": "4",
                                "nanos": 400_000_000,
                            }
                        ]
                    }
                },
            }
        ]
    }

    routes = parse_google_routes_response(payload)

    assert routes[0].toll_cost == Decimal("4.4")


def test_parse_google_routes_response_preserves_unknown_toll_price() -> None:
    payload = {
        "routes": [
            {
                "distanceMeters": 10_000,
                "duration": "900s",
                "travelAdvisory": {
                    "tollInfo": {},
                },
            }
        ]
    }

    routes = parse_google_routes_response(payload)

    assert routes[0].toll_cost is None


def test_parse_google_routes_response_does_not_convert_non_usd_toll() -> None:
    payload = {
        "routes": [
            {
                "distanceMeters": 10_000,
                "duration": "900s",
                "travelAdvisory": {
                    "tollInfo": {
                        "estimatedPrice": [
                            {
                                "currencyCode": "EUR",
                                "units": "3",
                            }
                        ]
                    }
                },
            }
        ]
    }

    routes = parse_google_routes_response(payload)

    assert routes[0].toll_cost is None


def test_parse_google_routes_response_does_not_collapse_multiple_currencies() -> None:
    payload = {
        "routes": [
            {
                "distanceMeters": 10_000,
                "duration": "900s",
                "travelAdvisory": {
                    "tollInfo": {
                        "estimatedPrice": [
                            {
                                "currencyCode": "USD",
                                "units": "2",
                            },
                            {
                                "currencyCode": "MXN",
                                "units": "40",
                            },
                        ]
                    }
                },
            }
        ]
    }

    routes = parse_google_routes_response(payload)

    assert routes[0].toll_cost is None


def test_parse_google_routes_response_rounds_fractional_duration() -> None:
    payload = {
        "routes": [
            {
                "distanceMeters": 10_000,
                "duration": "900.5s",
            }
        ]
    }

    routes = parse_google_routes_response(payload)

    assert routes[0].duration_seconds == 901


def test_parse_google_routes_response_rejects_malformed_duration() -> None:
    payload = {
        "routes": [
            {
                "distanceMeters": 10_000,
                "duration": "invalid",
            }
        ]
    }

    with pytest.raises(
        GoogleRoutesResponseError,
        match="duration",
    ):
        parse_google_routes_response(payload)


def test_build_google_routes_request_payload_maps_route_search_request() -> None:
    request = RouteSearchRequest(
        origin="UC San Diego",
        destination="San Diego International Airport",
    )

    payload = build_google_routes_request_payload(request)

    assert payload == {
        "origin": {
            "address": "UC San Diego",
        },
        "destination": {
            "address": "San Diego International Airport",
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": True,
        "extraComputations": ["TOLLS"],
    }


def test_build_google_routes_request_payload_preserves_endpoint_strings() -> None:
    request = RouteSearchRequest(
        origin="  Origin  ",
        destination="  Destination  ",
    )

    payload = build_google_routes_request_payload(request)

    assert payload["origin"] == {
        "address": "  Origin  ",
    }
    assert payload["destination"] == {
        "address": "  Destination  ",
    }


def test_build_google_routes_request_payload_does_not_set_departure_time() -> None:
    request = RouteSearchRequest(
        origin="Origin",
        destination="Destination",
    )

    payload = build_google_routes_request_payload(request)

    assert "departureTime" not in payload


def test_google_routes_field_mask_requests_only_required_route_fields() -> None:
    assert GOOGLE_ROUTES_FIELD_MASK == (
        "routes.distanceMeters,routes.duration,routes.travelAdvisory.tollInfo"
    )


def test_google_routes_provider_sends_expected_compute_routes_requests() -> None:
    request_payloads: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == GOOGLE_ROUTES_COMPUTE_URL

        assert request.headers["X-Goog-Api-Key"] == "test-api-key"
        assert request.headers["X-Goog-FieldMask"] == GOOGLE_ROUTES_FIELD_MASK
        assert request.headers["Content-Type"] == "application/json"

        request_payloads.append(json.loads(request.content))

        return httpx.Response(
            status_code=200,
            json={},
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as client:
        provider: RouteProvider = GoogleRoutesRouteProvider(
            api_key="test-api-key",
            client=client,
        )

        routes = provider.get_routes(
            RouteSearchRequest(
                origin="Origin",
                destination="Destination",
            )
        )

    assert tuple(routes) == ()

    assert request_payloads == [
        {
            "origin": {
                "address": "Origin",
            },
            "destination": {
                "address": "Destination",
            },
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
            "computeAlternativeRoutes": True,
            "extraComputations": ["TOLLS"],
        },
        {
            "origin": {
                "address": "Origin",
            },
            "destination": {
                "address": "Destination",
            },
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
            "computeAlternativeRoutes": True,
            "extraComputations": ["TOLLS"],
            "routeModifiers": {
                "avoidTolls": True,
            },
        },
    ]

def test_google_routes_provider_normalizes_fake_google_response_in_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
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
                        "travelAdvisory": {
                            "tollInfo": {
                                "estimatedPrice": [
                                    {
                                        "currencyCode": "USD",
                                        "units": "3",
                                        "nanos": 500_000_000,
                                    }
                                ]
                            }
                        },
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as client:
        provider = GoogleRoutesRouteProvider(
            api_key="test-api-key",
            client=client,
        )

        routes = provider.get_routes(
            RouteSearchRequest(
                origin="Origin",
                destination="Destination",
            )
        )

    assert routes == (
        RouteCandidate(
            distance_meters=10_000,
            duration_seconds=900,
            toll_cost=Decimal(0),
        ),
        RouteCandidate(
            distance_meters=12_000,
            duration_seconds=800,
            toll_cost=Decimal("3.5"),
        ),
    )


def test_google_routes_provider_wraps_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "connection failed",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as client:
        provider = GoogleRoutesRouteProvider(
            api_key="test-api-key",
            client=client,
        )

        with pytest.raises(
            GoogleRoutesTransportError,
            match="request failed",
        ):
            provider.get_routes(
                RouteSearchRequest(
                    origin="Origin",
                    destination="Destination",
                )
            )


def test_google_routes_provider_wraps_non_success_http_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=403,
            json={
                "error": {
                    "code": 403,
                    "message": "The request is missing a valid API key.",
                    "status": "PERMISSION_DENIED",
                }
            },
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as client:
        provider = GoogleRoutesRouteProvider(
            api_key="test-api-key",
            client=client,
        )

        with pytest.raises(GoogleRoutesHTTPError) as exc_info:
            provider.get_routes(
                RouteSearchRequest(
                    origin="Origin",
                    destination="Destination",
                )
            )

    assert exc_info.value.status_code == 403


def test_google_routes_provider_wraps_invalid_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=b"not-json",
            headers={
                "Content-Type": "application/json",
            },
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as client:
        provider = GoogleRoutesRouteProvider(
            api_key="test-api-key",
            client=client,
        )

        with pytest.raises(
            GoogleRoutesResponseError,
            match="not valid JSON",
        ):
            provider.get_routes(
                RouteSearchRequest(
                    origin="Origin",
                    destination="Destination",
                )
            )


def test_google_routes_provider_retries_transport_failure_then_succeeds() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        if attempts < 3:
            raise httpx.ConnectError(
                "connection failed",
                request=request,
            )

        return httpx.Response(
            status_code=200,
            json={},
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as client:
        provider = GoogleRoutesRouteProvider(
            api_key="test-api-key",
            client=client,
            sleeper=delays.append,
        )

        routes = provider.get_routes(
            RouteSearchRequest(
                origin="Origin",
                destination="Destination",
            )
        )

    assert routes == ()
    assert attempts == 4
    assert delays == [
        0.25,
        0.5,
    ]


def test_google_routes_provider_stops_retrying_transport_failure() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        raise httpx.ConnectError(
            "connection failed",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as client:
        provider = GoogleRoutesRouteProvider(
            api_key="test-api-key",
            client=client,
            sleeper=delays.append,
        )

        with pytest.raises(GoogleRoutesTransportError):
            provider.get_routes(
                RouteSearchRequest(
                    origin="Origin",
                    destination="Destination",
                )
            )

    assert attempts == 3
    assert delays == [
        0.25,
        0.5,
    ]


def test_google_routes_provider_retries_rate_limit_response() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            return httpx.Response(
                status_code=429,
                json={},
            )

        return httpx.Response(
            status_code=200,
            json={},
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as client:
        provider = GoogleRoutesRouteProvider(
            api_key="test-api-key",
            client=client,
            sleeper=delays.append,
        )

        routes = provider.get_routes(
            RouteSearchRequest(
                origin="Origin",
                destination="Destination",
            )
        )

    assert routes == ()
    assert attempts == 3
    assert delays == [
        0.25,
    ]


def test_google_routes_provider_retries_server_error_response() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            return httpx.Response(
                status_code=503,
                json={},
            )

        return httpx.Response(
            status_code=200,
            json={},
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as client:
        provider = GoogleRoutesRouteProvider(
            api_key="test-api-key",
            client=client,
            sleeper=delays.append,
        )

        routes = provider.get_routes(
            RouteSearchRequest(
                origin="Origin",
                destination="Destination",
            )
        )

    assert routes == ()
    assert attempts == 3
    assert delays == [
        0.25,
    ]


def test_google_routes_provider_does_not_retry_permanent_http_failure() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        return httpx.Response(
            status_code=403,
            json={},
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as client:
        provider = GoogleRoutesRouteProvider(
            api_key="test-api-key",
            client=client,
            sleeper=delays.append,
        )

        with pytest.raises(GoogleRoutesHTTPError) as exc_info:
            provider.get_routes(
                RouteSearchRequest(
                    origin="Origin",
                    destination="Destination",
                )
            )

    assert exc_info.value.status_code == 403
    assert attempts == 1
    assert delays == []

def test_build_google_routes_request_payload_can_request_avoid_tolls() -> None:
    request = RouteSearchRequest(
        origin="Origin",
        destination="Destination",
    )

    payload = build_google_routes_request_payload(
        request,
        avoid_tolls=True,
    )

    assert payload == {
        "origin": {
            "address": "Origin",
        },
        "destination": {
            "address": "Destination",
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": True,
        "extraComputations": ["TOLLS"],
        "routeModifiers": {
            "avoidTolls": True,
        },
    }

def test_google_routes_provider_merges_candidate_sets_in_stable_order() -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1

            if request_count == 1:
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
                                "travelAdvisory": {
                                    "tollInfo": {
                                        "estimatedPrice": [
                                            {
                                                "currencyCode": "USD",
                                                "units": "3",
                                            }
                                        ]
                                    }
                                },
                            },
                        ]
                    },
                )

            return httpx.Response(
                status_code=200,
                json={
                    "routes": [
                        {
                            "distanceMeters": 12_000,
                            "duration": "800s",
                            "travelAdvisory": {
                                "tollInfo": {
                                    "estimatedPrice": [
                                        {
                                            "currencyCode": "USD",
                                            "units": "3",
                                        }
                                    ]
                                }
                            },
                        },
                        {
                            "distanceMeters": 14_000,
                            "duration": "1_000s",
                            "travelAdvisory": {
                                "tollInfo": {
                                    "estimatedPrice": [
                                        {
                                            "currencyCode": "USD",
                                            "units": "1",
                                            "nanos": 250_000_000,
                                        }
                                    ]
                                }
                            },
                        },
                    ]
                },
            )

        transport = httpx.MockTransport(handler)

        with httpx.Client(transport=transport) as client:
            provider = GoogleRoutesRouteProvider(
                api_key="test-api-key",
                client=client,
            )

            routes = provider.get_routes(
                RouteSearchRequest(
                    origin="Origin",
                    destination="Destination",
                )
            )

        assert routes == (
            RouteCandidate(
                distance_meters=10_000,
                duration_seconds=900,
                toll_cost=Decimal(0),
            ),
            RouteCandidate(
                distance_meters=12_000,
                duration_seconds=800,
                toll_cost=Decimal(3),
            ),
            RouteCandidate(
                distance_meters=14_000,
                duration_seconds=1_000,
                toll_cost=Decimal("1.25"),
            ),
        )

def test_google_routes_provider_propagates_avoid_tolls_acquisition_failure() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        if request_count == 1:
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

        return httpx.Response(
            status_code=403,
            json={},
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as client:
        provider = GoogleRoutesRouteProvider(
            api_key="test-api-key",
            client=client,
        )

        with pytest.raises(GoogleRoutesHTTPError) as exc_info:
            provider.get_routes(
                RouteSearchRequest(
                    origin="Origin",
                    destination="Destination",
                )
            )

    assert exc_info.value.status_code == 403
    assert request_count == 2