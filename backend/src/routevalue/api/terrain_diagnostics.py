"""Read-only local terrain diagnostics. Never fetch routes or change configuration.

Default invocation reports configuration presence without revealing values or
making network calls. Route files are normalized API exports, not raw Google JSON.
"""

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.engine import Engine

from routevalue.api.schemas import RouteGeometryResponse, RouteResponse
from routevalue.api.terrain_status import build_v2_terrain_status
from routevalue.api.terrain_v2_acquisition import (
    TERRAIN_QUOTA_MODE_ENV,
    TERRAIN_SINGLE_PROCESS_DEV_ENV,
    build_optional_terrain_acquisition_service,
    configured_terrain_policy,
)
from routevalue.api.v2_evaluation_mappers import to_v2_trip_evaluation_response
from routevalue.api.vehicle_mass import VehicleMassUpdateRequest
from routevalue.application.models import ProvidedRoute, RouteGeometry, RoutePoint
from routevalue.application.terrain import TerrainAcquisitionResult, TerrainUnavailableReason
from routevalue.application.terrain_geometry_policy import evaluate_trip_terrain_geometry
from routevalue.application.terrain_preparation import prepare_trip_terrain_profiles
from routevalue.application.terrain_trip_evaluation import TerrainTripEvaluationOrchestrator
from routevalue.domain.models import (
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.infrastructure.elevation.safety import terrain_live_enabled
from routevalue.infrastructure.persistence.connection import create_application_engine


class DiagnosticRoute(BaseModel):
    """Only normalized routing facts are needed from an API response export."""

    route: RouteResponse
    geometry: RouteGeometryResponse | None = None


class DiagnosticRouteFile(BaseModel):
    """Bound input size and candidate count before external requests."""

    route_evaluations: list[DiagnosticRoute] = Field(min_length=1, max_length=6)


def configuration_report(environment: Mapping[str, str]) -> dict[str, object]:
    """Report presence only; no credentials, hosts, tokens, or URLs are returned."""
    return {
        "mode": "configuration_check",
        "network_calls": 0,
        "live_terrain_enabled": terrain_live_enabled(environment),
        "single_process_confirmed": environment.get(TERRAIN_SINGLE_PROCESS_DEV_ENV) == "1",
        "quota_mode": environment.get(TERRAIN_QUOTA_MODE_ENV, "process")
        if environment.get(TERRAIN_QUOTA_MODE_ENV, "process") in ("process", "postgres")
        else "invalid",
        "requests_per_trip": configured_terrain_policy(environment).max_requests_per_trip,
        "configured": {
            name: bool(environment.get(name, "").strip())
            for name in (
                "GOOGLE_ROUTES_API_KEY",
                "DATABASE_URL",
                "NEON_AUTH_BASE_URL",
                "NEON_AUTH_JWKS_URL",
            )
        },
    }


def read_routes(path: Path) -> tuple[ProvidedRoute, ...]:
    """Accept a bounded normalized route export without executing its content."""
    if path.stat().st_size > 2_000_000:
        raise ValueError("route export exceeds the two-megabyte diagnostic limit")
    payload = DiagnosticRouteFile.model_validate_json(path.read_bytes())
    return tuple(
        ProvidedRoute(
            route=RouteCandidate(
                distance_meters=item.route.distance_meters,
                duration_seconds=item.route.duration_seconds,
                toll_cost=item.route.toll_cost,
            ),
            geometry=RouteGeometry(
                points=tuple(
                    RoutePoint(
                        latitude=point.latitude,
                        longitude=point.longitude,
                    )
                    for point in item.geometry.points
                )
            )
            if item.geometry is not None
            else None,
        )
        for item in payload.route_evaluations
    )


def run_diagnostics(
    arguments: argparse.Namespace,
    *,
    client: httpx.Client,
) -> dict[str, object]:
    """Acquire elevation once, then compare both models to their exact baselines."""
    required = ("mpg", "gas_price", "kwh_per_mile", "electricity_price", "value_of_time")
    if any(getattr(arguments, name) is None for name in required):
        raise ValueError("route diagnostics require all vehicle efficiency and economic inputs")
    routes = read_routes(arguments.routes_file)
    mass = VehicleMassUpdateRequest(
        weight=arguments.mass_kg,
        unit="kg" if arguments.mass_kg is not None else None,
        source_reference="User-entered diagnostic curb weight"
        if arguments.mass_kg is not None
        else None,
    ).to_domain_mass()
    gasoline = GasolineVehicleSpecification(
        combined_mpg=arguments.mpg,
        fuel_grade=GasolineGrade.REGULAR,
        vehicle_mass=mass,
    )
    electric = ElectricVehicleSpecification(
        combined_kwh_per_mile=arguments.kwh_per_mile, vehicle_mass=mass
    )
    gas_quote = GasolinePriceQuote(
        price_per_gallon=arguments.gas_price,
        fuel_grade=GasolineGrade.REGULAR,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )
    electric_quote = ElectricityPriceQuote(price_per_kilowatt_hour=arguments.electricity_price)
    if not arguments.value_of_time.is_finite() or arguments.value_of_time < 0:
        raise ValueError("value of time must be finite and nonnegative")

    service = None
    if arguments.execute:
        if not arguments.confirm_high_quality_geometry:
            raise ValueError("live diagnostics require confirmation of HIGH_QUALITY route geometry")
        # Diagnostics may use durable accounting too; own/dispose that engine.
        service = build_optional_terrain_acquisition_service(
            client=client, engine_factory=_diagnostic_engine
        )
        if service is None:
            raise ValueError("live terrain must be explicitly enabled in the local environment")

    acquisitions = (
        service.acquire_routes(routes)
        if service is not None
        else tuple(
            TerrainAcquisitionResult(
                route_index=index, unavailable_reason=TerrainUnavailableReason.DISABLED
            )
            for index in range(len(routes))
        )
    )
    profiles = prepare_trip_terrain_profiles(routes, acquisitions)
    geometry = evaluate_trip_terrain_geometry(profiles)
    safe_profiles = profiles if geometry.allowed else (None,) * len(routes)
    evaluator = TerrainTripEvaluationOrchestrator()
    report: dict[str, object] = {
        "mode": "live_elevation" if arguments.execute else "offline_baseline",
        "google_routes_calls": 0,
        "geometry_confirmation_is_user_supplied": bool(arguments.confirm_high_quality_geometry),
        "limitations": "Terrain samples are not measured road grades. This report does not establish universal coverage or model accuracy.",
    }
    for kind in ("gasoline", "electricity"):
        if kind == "gasoline":
            result = evaluator.evaluate_gasoline_trip(
                routes,
                terrain_profiles=safe_profiles,
                vehicle=gasoline,
                fuel_price_quote=gas_quote,
                value_of_time_per_hour=arguments.value_of_time,
            )
            baseline = evaluator.evaluate_gasoline_trip(
                routes,
                terrain_profiles=(None,) * len(routes),
                vehicle=gasoline,
                fuel_price_quote=gas_quote,
                value_of_time_per_hour=arguments.value_of_time,
            )
        else:
            result = evaluator.evaluate_electric_trip(
                routes,
                terrain_profiles=safe_profiles,
                vehicle=electric,
                electricity_price_quote=electric_quote,
                value_of_time_per_hour=arguments.value_of_time,
            )
            baseline = evaluator.evaluate_electric_trip(
                routes,
                terrain_profiles=(None,) * len(routes),
                vehicle=electric,
                electricity_price_quote=electric_quote,
                value_of_time_per_hour=arguments.value_of_time,
            )
        status = build_v2_terrain_status(
            acquisitions=acquisitions,
            geometry_decision=geometry,
            terrain_energy=result.terrain_energy,
        )
        response = to_v2_trip_evaluation_response(result.trip, terrain_status=status)
        report[kind] = {
            "terrain_status": status.model_dump(mode="json"),
            "energy": [
                item.energy_estimate.model_dump(mode="json") if item.energy_estimate else None
                for item in response.route_evaluations
            ],
            "baseline_costs": [
                str(item.energy_estimate.cost) if item.energy_estimate else None
                for item in baseline.trip.route_evaluations
            ],
        }
    return report


_engine: Engine | None = None


def _diagnostic_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_application_engine()
    return _engine


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes-file", type=Path)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Allow guarded public OpenTopoData elevation calls; never calls Google",
    )
    parser.add_argument("--confirm-high-quality-geometry", action="store_true")
    parser.add_argument("--mass-kg", type=Decimal)
    for name in ("mpg", "gas-price", "kwh-per-mile", "electricity-price", "value-of-time"):
        parser.add_argument(f"--{name}", type=Decimal)
    arguments = parser.parse_args(argv)
    try:
        if arguments.routes_file is None:
            if arguments.execute:
                raise ValueError("--execute requires a normalized route export")
            report = configuration_report(os.environ)
        else:
            with httpx.Client(timeout=15) as client:
                report = run_diagnostics(arguments, client=client)
    except (OSError, ValueError, ValidationError):
        # Validation exceptions can contain raw input; never print their bodies.
        print(
            json.dumps(
                {
                    "error": "Invalid or incomplete diagnostic inputs/configuration. Check the local terrain guide."
                }
            )
        )
        return 2
    finally:
        global _engine
        if _engine is not None:
            _engine.dispose()
            _engine = None
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
