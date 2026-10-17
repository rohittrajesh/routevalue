"""Network-free tests for M9 guarded elevation composition."""

import json
from decimal import Decimal

import httpx
import pytest

from routevalue.api.terrain_v2_acquisition import (
    TERRAIN_SINGLE_PROCESS_DEV_ENV,
    build_optional_terrain_acquisition_service,
)
from routevalue.application.models import (
    ProvidedRoute,
    RouteGeometry,
    RoutePoint,
)
from routevalue.application.terrain import (
    GeometryFidelity,
    TerrainAcquisitionStatus,
)
from routevalue.application.terrain_geometry_policy import (
    TerrainGeometryReason,
    evaluate_trip_terrain_geometry,
)
from routevalue.application.terrain_preparation import prepare_trip_terrain_profiles
from routevalue.domain.models import RouteCandidate
from routevalue.infrastructure.elevation.safety import TERRAIN_LIVE_ENABLED_ENV


def _route() -> ProvidedRoute:
    return ProvidedRoute(
        route=RouteCandidate(
            distance_meters=1000,
            duration_seconds=120,
            toll_cost=Decimal(0),
        ),
        geometry=RouteGeometry(
            points=(
                RoutePoint(latitude=32.0, longitude=-117.0),
                RoutePoint(latitude=32.01, longitude=-117.01),
            )
        ),
    )


def test_default_configuration_cannot_access_elevation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TERRAIN_LIVE_ENABLED_ENV, raising=False)
    monkeypatch.delenv(TERRAIN_SINGLE_PROCESS_DEV_ENV, raising=False)

    def forbidden_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Disabled acquisition must not send HTTP requests")

    with httpx.Client(transport=httpx.MockTransport(forbidden_request)) as client:
        service = build_optional_terrain_acquisition_service(client=client)

    assert service is None


def test_live_setting_requires_single_process_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TERRAIN_LIVE_ENABLED_ENV, "1")
    monkeypatch.delenv(TERRAIN_SINGLE_PROCESS_DEV_ENV, raising=False)

    with (
        httpx.Client() as client,
        pytest.raises(ValueError, match="single-process development"),
    ):
        build_optional_terrain_acquisition_service(client=client)


def test_invalid_live_setting_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TERRAIN_LIVE_ENABLED_ENV, "yes")
    monkeypatch.setenv(TERRAIN_SINGLE_PROCESS_DEV_ENV, "1")

    with (
        httpx.Client() as client,
        pytest.raises(ValueError, match=TERRAIN_LIVE_ENABLED_ENV),
    ):
        build_optional_terrain_acquisition_service(client=client)


def test_local_opt_in_uses_guarded_provider_and_detailed_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TERRAIN_LIVE_ENABLED_ENV, "1")
    monkeypatch.setenv(TERRAIN_SINGLE_PROCESS_DEV_ENV, "1")

    requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        assert request.method == "POST"
        assert request.url.path == "/v1/ned10m"

        payload: object = json.loads(request.content)
        assert isinstance(payload, dict)

        coordinates = payload.get("locations")
        assert isinstance(coordinates, str)

        results: list[dict[str, object]] = []

        for pair in coordinates.split("|"):
            latitude_text, longitude_text = pair.split(",")

            results.append(
                {
                    "location": {
                        "lat": float(latitude_text),
                        "lng": float(longitude_text),
                    },
                    "elevation": 100,
                    "dataset": "ned10m",
                }
            )

        return httpx.Response(
            200,
            json={
                "status": "OK",
                "results": results,
            },
        )

    routes = (_route(),)

    with httpx.Client(transport=httpx.MockTransport(handle_request)) as client:
        service = build_optional_terrain_acquisition_service(client=client)

        assert service is not None
        acquisitions = service.acquire_routes(routes)

    assert len(requests) == 1
    assert len(acquisitions) == 1
    assert acquisitions[0].status is TerrainAcquisitionStatus.COMPLETE

    profile = acquisitions[0].profile
    assert profile is not None
    assert profile.geometry_fidelity is GeometryFidelity.DETAILED

    prepared = prepare_trip_terrain_profiles(routes, acquisitions)
    decision = evaluate_trip_terrain_geometry(prepared)

    assert decision.allowed is True
    assert decision.reason is TerrainGeometryReason.ACCEPTED
