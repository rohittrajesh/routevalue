"""Read-only diagnostic, budget allocation and browser-boundary regressions."""

import argparse
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from browser_server import create_browser_app
from fastapi.testclient import TestClient

from routevalue.api import terrain_v2_acquisition as composition
from routevalue.api.terrain_diagnostics import configuration_report, main, run_diagnostics
from routevalue.application.models import ProvidedRoute, RouteGeometry, RoutePoint
from routevalue.application.terrain import TerrainAcquisitionStatus
from routevalue.domain.models import RouteCandidate
from routevalue.infrastructure.elevation.safety import (
    PublicElevationCallGate,
    PublicElevationPolicy,
)


def test_preflight_never_exposes_configuration_values() -> None:
    secret = "not-a-real-secret-but-must-not-be-printed"
    report = configuration_report({"GOOGLE_ROUTES_API_KEY": secret})
    assert secret not in json.dumps(report)
    assert report["network_calls"] == 0
    assert report["live_terrain_enabled"] is False


def _arguments(tmp_path: Path, *, execute: bool = False) -> argparse.Namespace:
    route_file = tmp_path / "routes.json"
    route_file.write_text(
        json.dumps(
            {
                "route_evaluations": [
                    {
                        "route": {
                            "distance_meters": 10000,
                            "duration_seconds": 900,
                            "toll_cost": "0",
                        },
                        "geometry": {
                            "points": [
                                {"latitude": 32.7, "longitude": -117.1},
                                {"latitude": 32.8, "longitude": -117.0},
                            ]
                        },
                    }
                ]
            }
        )
    )
    return argparse.Namespace(
        routes_file=route_file,
        execute=execute,
        confirm_high_quality_geometry=False,
        mass_kg=Decimal(1800),
        mpg=Decimal(30),
        gas_price=Decimal("4.5"),
        kwh_per_mile=Decimal("0.3"),
        electricity_price=Decimal("0.25"),
        value_of_time=Decimal(24),
    )


def test_offline_route_diagnostics_cannot_call_network(tmp_path: Path) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("offline diagnostics attempted network")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        report = run_diagnostics(_arguments(tmp_path), client=client)
    for kind in ("gasoline", "electricity"):
        outcome = report[kind]
        assert isinstance(outcome, dict)
        assert outcome["terrain_status"]["terrain_applied"] is False
        assert outcome["energy"][0]["cost"] == outcome["baseline_costs"][0]


def test_execute_requires_explicit_geometry_confirmation_before_network(tmp_path: Path) -> None:
    with httpx.Client() as client, pytest.raises(ValueError, match="HIGH_QUALITY"):
        run_diagnostics(_arguments(tmp_path, execute=True), client=client)


def test_cli_rejects_execute_without_routes(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--execute"]) == 2
    assert "Invalid or incomplete" in capsys.readouterr().out


def test_browser_fixture_requires_test_only_enablement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ROUTEVALUE_BROWSER_TEST_SERVER", raising=False)
    with pytest.raises(RuntimeError, match="test-only"):
        create_browser_app()


def test_browser_fixture_still_requires_its_explicit_synthetic_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROUTEVALUE_BROWSER_TEST_SERVER", "1")
    with TestClient(create_browser_app()) as client:
        assert client.get("/api/v2/me").status_code == 401
        assert (
            client.get("/api/v2/me", headers={"Authorization": "Bearer anything"}).status_code
            == 401
        )


def test_live_composition_reuses_identical_shapes_and_resets_only_trip_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROUTEVALUE_TERRAIN_LIVE_ENABLED", "1")
    monkeypatch.setenv("ROUTEVALUE_TERRAIN_SINGLE_PROCESS_DEV", "1")
    clock = [0.0]
    gate = PublicElevationCallGate(
        enabled=True,
        policy=PublicElevationPolicy(max_requests_per_trip=5, max_requests_per_24_hours=6),
        clock=lambda: clock[0],
        sleeper=lambda delay: clock.__setitem__(0, clock[0] + delay),
    )
    monkeypatch.setattr(composition, "_shared_elevation_gate", lambda policy: gate)
    calls: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        coordinates = json.loads(request.content)["locations"].split("|")
        calls.append(len(coordinates))
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "results": [
                    {
                        "location": dict(
                            zip(("lat", "lng"), map(float, coordinate.split(",")), strict=True)
                        ),
                        "elevation": 100,
                        "dataset": "ned10m",
                    }
                    for coordinate in coordinates
                ],
            },
        )

    routes = tuple(
        ProvidedRoute(
            route=RouteCandidate(
                distance_meters=90000 + index * 1000, duration_seconds=3600, toll_cost=Decimal(0)
            ),
            geometry=RouteGeometry(
                points=(
                    RoutePoint(latitude=32.7, longitude=-117.1),
                    RoutePoint(latitude=33 + index / 100, longitude=-116.5),
                )
            ),
        )
        for index in range(3)
    )
    # Duplicate geometry with different economic facts must not spend another call.
    duplicate = replace(routes[0], route=replace(routes[0].route, duration_seconds=3700))
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        service = composition.build_optional_terrain_acquisition_service(client=client)
        assert service is not None
        for _ in range(2):
            result = service.acquire_routes((*routes, duplicate))
            assert [item.route_index for item in result] == [0, 1, 2, 3]
            assert all(item.status is TerrainAcquisitionStatus.COMPLETE for item in result)
            assert result[0].profile == result[3].profile
        blocked = service.acquire_routes(routes)
    assert len(calls) == 6
    assert max(calls) <= 100
    assert all(item.status is TerrainAcquisitionStatus.UNAVAILABLE for item in blocked)
