"""Loopback-only Playwright fixture application, never production composition.

Real HTTP routes and application services; deterministic external providers and
in-memory storage. Does not read credentials or open external network connections.
"""

import os
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, Request

from routevalue.api.errors import AuthenticationRequiredError
from routevalue.api.preferences import get_user_preferences_repository
from routevalue.api.saved_vehicles import (
    get_saved_vehicle_repository,
    get_vehicle_specification_provider,
)
from routevalue.api.terrain_v2_composition import build_terrain_v2_evaluation_service
from routevalue.api.terrain_v2_service import TerrainV2EvaluationService
from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_trip_evaluations import get_profile_driven_trip_evaluation_service
from routevalue.api.vehicle_mass import get_user_vehicle_mass_service
from routevalue.application.gasoline_price_geography import (
    PricingJurisdiction,
    PricingJurisdictionResult,
)
from routevalue.application.gasoline_price_ports import GasolinePriceLookupRequest
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteGeometry,
    RoutePoint,
    RouteSearchRequest,
    VehicleCatalogConfiguration,
    VehicleSpecificationLookupResult,
)
from routevalue.application.preferences import UserPreferences
from routevalue.application.saved_vehicles import SavedVehicle, SavedVehicleSnapshot
from routevalue.application.terrain import ElevationSample, GeometryFidelity
from routevalue.application.terrain_acquisition import TerrainAcquisitionService
from routevalue.application.terrain_sampling import TerrainSampleLocation
from routevalue.application.vehicle_mass_update import UserVehicleMassService
from routevalue.domain.gasoline_price_metadata import GasolineMarketMetadata
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.vehicle_mass import VehicleMass
from routevalue.main import create_app


class BrowserStore:
    def __init__(self) -> None:
        self.preferences: dict[UserId, UserPreferences] = {}
        self.vehicles: dict[tuple[UserId, SavedVehicleId], SavedVehicle] = {}

    def get_preferences(self, user_id: UserId) -> UserPreferences:
        return self.preferences.get(user_id, UserPreferences())

    def save_preferences(self, user_id: UserId, preferences: UserPreferences) -> UserPreferences:
        self.preferences[user_id] = preferences
        return preferences

    def list_vehicles(self, user_id: UserId) -> Sequence[SavedVehicle]:
        return tuple(vehicle for (owner, _), vehicle in self.vehicles.items() if owner == user_id)

    def get_vehicle(self, user_id: UserId, vehicle_id: SavedVehicleId) -> SavedVehicle | None:
        return self.vehicles.get((user_id, vehicle_id))

    def create_vehicle(self, user_id: UserId, snapshot: SavedVehicleSnapshot) -> SavedVehicle:
        vehicle = SavedVehicle(
            id=SavedVehicleId(value=uuid4()),
            configuration=snapshot.configuration,
            specification=snapshot.specification,
            specification_retrieved_at=snapshot.specification_retrieved_at,
            saved_at=datetime.now(UTC),
        )
        self.vehicles[user_id, vehicle.id] = vehicle
        return vehicle

    def delete_vehicle(self, user_id: UserId, vehicle_id: SavedVehicleId) -> bool:
        if self.vehicles.pop((user_id, vehicle_id), None) is None:
            return False
        preferences = self.get_preferences(user_id)
        if preferences.default_vehicle_id == vehicle_id:
            self.preferences[user_id] = replace(preferences, default_vehicle_id=None)
        return True

    def update_vehicle_mass(
        self, user_id: UserId, vehicle_id: SavedVehicleId, mass: VehicleMass | None
    ) -> SavedVehicle | None:
        vehicle = self.get_vehicle(user_id, vehicle_id)
        if vehicle is None:
            return None
        updated = replace(vehicle, specification=replace(vehicle.specification, vehicle_mass=mass))
        self.vehicles[user_id, vehicle_id] = updated
        return updated


class BrowserCatalog:
    def list_years(self) -> Sequence[int]:
        return (2025,)

    def list_makes(self, *, year: int) -> Sequence[str]:
        return ("Example",) if year == 2025 else ()

    def list_models(self, *, year: int, make: str) -> Sequence[str]:
        return ("Gasoline", "Electric") if year == 2025 and make == "Example" else ()

    def list_configurations(
        self, *, year: int, make: str, model: str
    ) -> Sequence[VehicleCatalogConfiguration]:
        return (
            (
                VehicleCatalogConfiguration(
                    year=year,
                    make=make,
                    model=model,
                    configuration="Standard",
                    source="browser_fixture",
                    source_id=model,
                ),
            )
            if model in self.list_models(year=year, make=make)
            else ()
        )

    def get_specification(
        self, configuration: VehicleCatalogConfiguration
    ) -> VehicleSpecificationLookupResult:
        return VehicleSpecificationLookupResult(
            specification=(
                ElectricVehicleSpecification(combined_kwh_per_mile=Decimal("0.30"))
                if configuration.model == "Electric"
                else GasolineVehicleSpecification(
                    combined_mpg=Decimal(30), fuel_grade=GasolineGrade.REGULAR
                )
            ),
            unavailable_reason=None,
        )


class BrowserRoutes:
    def get_routes(self, request: RouteSearchRequest) -> Sequence[ProvidedRoute]:
        return tuple(
            ProvidedRoute(
                route=RouteCandidate(
                    distance_meters=10000 + index * 1000,
                    duration_seconds=900 + index * 100,
                    toll_cost=Decimal(0),
                ),
                geometry=RouteGeometry(
                    points=(
                        RoutePoint(
                            latitude=request.origin.latitude, longitude=request.origin.longitude
                        ),
                        RoutePoint(
                            latitude=request.destination.latitude,
                            longitude=request.destination.longitude,
                        ),
                    )
                ),
            )
            for index in range(2)
        )


class BrowserElevation:
    def __init__(self, *, missing: bool) -> None:
        self.missing = missing

    def get_elevations(
        self, locations: Sequence[TerrainSampleLocation]
    ) -> tuple[ElevationSample, ...]:
        return tuple(
            ElevationSample(
                point=location.point,
                distance_meters=location.distance_meters,
                elevation_meters=None
                if self.missing
                else Decimal(100) + Decimal(location.distance_meters) / Decimal(50),
            )
            for location in locations
        )


class BrowserJurisdiction:
    def resolve(self, location: ResolvedLocation) -> PricingJurisdictionResult:
        return PricingJurisdictionResult(jurisdiction=PricingJurisdiction.CALIFORNIA)


class BrowserPrices:
    def __init__(self, *, missing: bool) -> None:
        self.missing = missing

    def get_price(self, request: GasolinePriceLookupRequest) -> GasolinePriceQuote | None:
        if self.missing:
            return None
        return GasolinePriceQuote(
            price_per_gallon=Decimal("4.125"),
            fuel_grade=request.fuel_grade,
            source=GasolinePriceSource.REGIONAL_MARKET,
            observed_at=datetime(2026, 10, 19, tzinfo=UTC),
            market_metadata=GasolineMarketMetadata(provider="EIA", geography=request.geography),
        )


def create_browser_app() -> FastAPI:
    """Only the dedicated test runner may create this fixture application."""
    if os.environ.get("ROUTEVALUE_BROWSER_TEST_SERVER") != "1":
        raise RuntimeError("Browser fixture server requires explicit test-only enablement")
    app = create_app()
    store = BrowserStore()

    def user(authorization: Annotated[str | None, Header()] = None) -> AuthenticatedUser:
        if authorization is None or not authorization.startswith("Bearer browser-test:"):
            raise AuthenticationRequiredError
        try:
            return AuthenticatedUser(
                user_id=UserId(value=UUID(authorization.removeprefix("Bearer browser-test:")))
            )
        except ValueError:
            raise AuthenticationRequiredError from None

    def evaluation(request: Request) -> TerrainV2EvaluationService:
        return build_terrain_v2_evaluation_service(
            preferences_repository=store,
            saved_vehicle_repository=store,
            route_provider=BrowserRoutes(),
            terrain_acquisition_service=TerrainAcquisitionService(
                elevation_provider=BrowserElevation(
                    missing=request.cookies.get("fixture_terrain") == "missing"
                ),
                enabled=True,
                geometry_fidelity=GeometryFidelity.DETAILED,
            ),
            gasoline_price_provider=BrowserPrices(
                missing=request.cookies.get("fixture_price") == "missing"
            ),
            gasoline_jurisdiction_resolver=BrowserJurisdiction(),
            pricing_clock=lambda: datetime(2026, 10, 19, 12, tzinfo=UTC),
        )

    app.dependency_overrides[get_authenticated_user] = user
    app.dependency_overrides[get_saved_vehicle_repository] = lambda: store
    app.dependency_overrides[get_user_preferences_repository] = lambda: store
    app.dependency_overrides[get_vehicle_specification_provider] = BrowserCatalog
    app.dependency_overrides[get_user_vehicle_mass_service] = lambda: UserVehicleMassService(
        repository=store
    )
    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = evaluation
    return app
