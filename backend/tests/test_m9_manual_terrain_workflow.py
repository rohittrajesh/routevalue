"""Offline HTTP workflow coverage; coordinates are real, road/elevation data synthetic.

These cases establish integration across US locations, not live provider coverage
or calibrated predictions. No Google, Neon, EIA, or elevation network calls occur.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from routevalue.api.terrain_v2_composition import build_terrain_v2_evaluation_service
from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_evaluation_schemas import V2TripEvaluationResponse
from routevalue.api.v2_trip_evaluations import get_profile_driven_trip_evaluation_service
from routevalue.api.vehicle_mass import get_user_vehicle_mass_service
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.models import (
    ProvidedRoute,
    RouteGeometry,
    RoutePoint,
    VehicleCatalogConfiguration,
)
from routevalue.application.ports import (
    RouteProvider,
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.application.preferences import UserPreferences
from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.application.terrain import GeometryFidelity
from routevalue.application.terrain_acquisition import TerrainAcquisitionService
from routevalue.application.vehicle_mass_update import UserVehicleMassService
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.units import meters_to_miles
from routevalue.domain.vehicle_mass import VehicleMass
from routevalue.infrastructure.elevation.open_topo_data import OpenTopoDataElevationProvider
from routevalue.main import create_app

type Scenario = Literal[
    "uphill", "downhill", "flat", "missing", "partial", "quota", "malformed", "untrusted"
]


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        pytest.param(32.72, -117.16, id="san-diego"),
        pytest.param(39.74, -104.99, id="denver"),
        pytest.param(35.60, -82.55, id="asheville"),
        pytest.param(41.88, -87.63, id="chicago"),
        pytest.param(61.22, -149.90, id="anchorage"),
        pytest.param(21.31, -157.86, id="honolulu"),
    ],
)
@pytest.mark.parametrize("electric", [False, True], ids=["gasoline", "bev"])
@pytest.mark.parametrize(
    "scenario",
    ["uphill", "downhill", "flat", "missing", "partial", "quota", "malformed", "untrusted"],
)
def test_manual_mass_lifecycle_and_terrain_http_contract(
    latitude: float,
    longitude: float,
    electric: bool,
    scenario: Scenario,
) -> None:
    owner = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())
    now = datetime(2026, 10, 19, tzinfo=UTC)
    vehicle = SavedVehicle(
        id=vehicle_id,
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Fixture",
            model="Synthetic",
            configuration="Test",
            source="test",
            source_id="fixture",
        ),
        specification=(
            ElectricVehicleSpecification(combined_kwh_per_mile=Decimal("0.30"))
            if electric
            else GasolineVehicleSpecification(
                combined_mpg=Decimal(30), fuel_grade=GasolineGrade.REGULAR
            )
        ),
        specification_retrieved_at=now,
        saved_at=now,
    )
    preferences = Mock(spec=UserPreferencesRepository)
    preferences.get_preferences.return_value = UserPreferences(
        value_of_time_per_hour=Decimal(24),
        default_vehicle_id=vehicle_id,
    )
    vehicles = Mock(spec=SavedVehicleRepository)
    vehicles.get_vehicle.side_effect = lambda user, identifier: (
        vehicle if (user, identifier) == (owner, vehicle_id) else None
    )

    def update_mass(
        user: UserId, identifier: SavedVehicleId, mass: VehicleMass | None
    ) -> SavedVehicle | None:
        nonlocal vehicle
        if (user, identifier) != (owner, vehicle_id):
            return None
        vehicle = replace(vehicle, specification=replace(vehicle.specification, vehicle_mass=mass))
        return vehicle

    mass_repository = Mock()
    mass_repository.update_vehicle_mass.side_effect = update_mass
    routing = Mock(spec=RouteProvider)
    points = (
        RoutePoint(latitude=latitude, longitude=longitude),
        RoutePoint(latitude=latitude + 0.05, longitude=longitude + 0.05),
    )
    routing.get_routes.return_value = tuple(
        ProvidedRoute(
            route=RouteCandidate(
                distance_meters=10000, duration_seconds=900 + index * 60, toll_cost=Decimal(0)
            ),
            geometry=RouteGeometry(points=points),
        )
        for index in range(2)
    )
    calls = 0

    def elevation_response(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        # Both short routes fit into one batch each. Reset for each evaluation.
        index = calls % 2
        calls += 1
        if index == 1 and scenario == "quota":
            return httpx.Response(429)
        if index == 1 and scenario == "malformed":
            return httpx.Response(200, json={"status": "OK", "results": []})
        coordinates = json.loads(request.content)["locations"].split("|")
        direction = -1 if scenario == "downhill" else 0 if scenario == "flat" else 1
        results = []
        for offset, coordinate in enumerate(coordinates):
            lat, lon = map(float, coordinate.split(","))
            elevation = 1000 + direction * 200 * offset / (len(coordinates) - 1)
            missing = index == 1 and (
                scenario == "missing" or (scenario == "partial" and offset > len(coordinates) // 2)
            )
            results.append(
                {
                    "location": {"lat": lat, "lng": lon},
                    "elevation": None if missing else elevation,
                    "dataset": "ned10m",
                }
            )
        return httpx.Response(200, json={"status": "OK", "results": results})

    with httpx.Client(transport=httpx.MockTransport(elevation_response)) as elevation_http:
        service = build_terrain_v2_evaluation_service(
            preferences_repository=preferences,
            saved_vehicle_repository=vehicles,
            route_provider=routing,
            terrain_acquisition_service=TerrainAcquisitionService(
                elevation_provider=OpenTopoDataElevationProvider(client=elevation_http),
                enabled=True,
                geometry_fidelity=GeometryFidelity.SIMPLIFIED
                if scenario == "untrusted"
                else GeometryFidelity.DETAILED,
            ),
        )
        app = create_app()
        app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=owner)
        app.dependency_overrides[get_profile_driven_trip_evaluation_service] = lambda: service
        app.dependency_overrides[get_user_vehicle_mass_service] = lambda: UserVehicleMassService(
            repository=mass_repository
        )
        request_body = {
            "origin": {
                "display_name": "Synthetic origin",
                "latitude": latitude,
                "longitude": longitude,
            },
            "destination": {
                "display_name": "Synthetic destination",
                "latitude": latitude + 0.05,
                "longitude": longitude + 0.05,
            },
            "electricity" if electric else "gasoline": {
                "price_per_kilowatt_hour" if electric else "fuel_price_per_gallon": "0.25"
                if electric
                else "4.50"
            },
        }

        with TestClient(app) as client:

            def evaluate() -> V2TripEvaluationResponse:
                nonlocal calls
                calls = 0
                response = client.post("/api/v2/trip-evaluations", json=request_body)
                assert response.status_code == 200, response.text
                assert calls == 2
                return V2TripEvaluationResponse.model_validate_json(response.content)

            baseline = evaluate()
            assert baseline.terrain_status is not None
            assert not baseline.terrain_status.terrain_applied
            assert "missing_vehicle_mass" in baseline.terrain_status.fallback_reasons
            path = f"/api/v2/vehicles/{vehicle_id.value}/mass"
            saved = client.patch(
                path,
                json={"weight": "1800", "unit": "kg", "source_reference": "Synthetic owner entry"},
            )
            assert saved.status_code == 200
            assert saved.json()["vehicle_mass"]["source"] == "user_provided"
            adjusted = evaluate()
            status = adjusted.terrain_status
            assert status is not None
            applicable = scenario in ("uphill", "downhill", "flat")
            assert status.terrain_applied is applicable
            assert adjusted.decision.eligible_count == 2
            assert (
                len(status.route_acquisition_statuses) == len(status.route_coverage_fractions) == 2
            )
            if applicable:
                assert status.fallback_reasons == []
                assert status.route_coverage_fractions == [Decimal(1), Decimal(1)]
            else:
                expected_reason = {
                    "partial": "insufficient_coverage",
                    "untrusted": "untrusted_geometry",
                }.get(scenario, "elevation_unavailable")
                assert expected_reason in status.fallback_reasons

            for original, current in zip(
                baseline.route_evaluations, adjusted.route_evaluations, strict=True
            ):
                before, after = original.energy_estimate, current.energy_estimate
                assert before is not None and after is not None
                expected_baseline = (
                    meters_to_miles(10000) * Decimal("0.30")
                    if electric
                    else meters_to_miles(10000) / Decimal(30)
                )
                price = Decimal("0.25") if electric else Decimal("4.50")
                assert before.cost == expected_baseline * price
                consumption = after.consumption
                assert consumption is not None
                quantity = (
                    consumption.kilowatt_hours
                    if consumption.energy_type == "electricity"
                    else consumption.gallons
                )
                assert after.cost == quantity * price
                if scenario == "uphill":
                    assert after.cost > before.cost
                elif scenario == "downhill":
                    assert Decimal(0) <= after.cost < before.cost
                else:
                    assert after == before
                breakdown = current.cost_breakdown
                assert breakdown is not None
                assert breakdown.generalized_cost == after.cost + Decimal(
                    current.route.duration_seconds
                ) / Decimal(3600) * Decimal(24)

            assert client.patch(path, json={"weight": None}).status_code == 200
            cleared = evaluate()
            assert cleared == baseline
