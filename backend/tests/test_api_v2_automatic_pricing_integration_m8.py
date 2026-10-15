"""Authenticated V2 automatic EIA gasoline pricing HTTP integration tests.

Exercises real application composition, quote selection, geographic
fallback, and trip evaluation without external HTTP or database access.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from routevalue.api.terrain_v2_composition import (
    build_terrain_v2_evaluation_service,
)
from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_trip_evaluations import (
    get_profile_driven_trip_evaluation_service,
)
from routevalue.application.gasoline_price_geography import (
    PricingJurisdiction,
    PricingJurisdictionResolver,
    PricingJurisdictionResult,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteSearchRequest,
    VehicleCatalogConfiguration,
)
from routevalue.application.ports import (
    RouteProvider,
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.application.preferences import UserPreferences
from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_quote_normalization import (
    normalize_eia_observations,
)
from routevalue.infrastructure.pricing.eia_snapshot_cache import (
    EiaPricingSnapshot,
)
from routevalue.infrastructure.pricing.eia_snapshot_price_provider import (
    PostgresEiaGasolinePriceProvider,
)
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaGasolineObservation,
)
from routevalue.main import create_app

_PATH = "/api/v2/trip-evaluations"

AS_OF = datetime(2026, 10, 14, 12, tzinfo=UTC)
OBSERVED_ON = date(2026, 10, 12)

ROUTE_DISTANCE_METERS = 160_934
METERS_PER_MILE = Decimal("1609.344")
TEST_GASOLINE_MPG = Decimal(25)
TEST_ELECTRIC_KWH_PER_MILE = Decimal("0.30")
COST_TOLERANCE = Decimal("0.001")


class FakeRoutes:
    def __init__(self) -> None:
        self.calls: list[RouteSearchRequest] = []

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[ProvidedRoute]:
        self.calls.append(request)

        return (
            ProvidedRoute(
                route=RouteCandidate(
                    distance_meters=ROUTE_DISTANCE_METERS,
                    duration_seconds=3600,
                    toll_cost=Decimal(0),
                ),
            ),
        )


class FakeSnapshotReader:
    def __init__(
        self,
        snapshots: dict[EiaGasolineRegion, EiaPricingSnapshot],
    ) -> None:
        self.snapshots = snapshots
        self.reads: list[EiaGasolineRegion] = []

    def get_snapshot(
        self,
        region: EiaGasolineRegion,
    ) -> EiaPricingSnapshot | None:
        self.reads.append(region)
        return self.snapshots.get(region)


class FakeJurisdictionResolver:
    def __init__(
        self,
        jurisdiction: PricingJurisdiction,
    ) -> None:
        self.jurisdiction = jurisdiction
        self.calls: list[ResolvedLocation] = []

    def resolve(
        self,
        location: ResolvedLocation,
    ) -> PricingJurisdictionResult:
        self.calls.append(location)
        return PricingJurisdictionResult(
            jurisdiction=self.jurisdiction,
        )


def make_snapshot(
    region: EiaGasolineRegion,
    *,
    regular: str,
    midgrade: str,
    premium: str,
    observed_on: date = OBSERVED_ON,
) -> EiaPricingSnapshot:
    prices = {
        GasolineGrade.REGULAR: Decimal(regular),
        GasolineGrade.MIDGRADE: Decimal(midgrade),
        GasolineGrade.PREMIUM: Decimal(premium),
    }

    observations = tuple(
        EiaGasolineObservation(
            series_id=region.series_for_grade(grade),
            fuel_grade=grade,
            observed_on=observed_on,
            price_per_gallon=prices[grade],
        )
        for grade in GasolineGrade
    )

    return EiaPricingSnapshot(
        region=region,
        quotes=normalize_eia_observations(
            observations=observations,
            region=region,
        ),
        refreshed_at=AS_OF,
    )


def make_vehicle(
    vehicle_id: SavedVehicleId,
    *,
    grade: GasolineGrade = GasolineGrade.REGULAR,
    electric: bool = False,
) -> SavedVehicle:
    specification = (
        ElectricVehicleSpecification(
            combined_kwh_per_mile=TEST_ELECTRIC_KWH_PER_MILE,
        )
        if electric
        else GasolineVehicleSpecification(
            combined_mpg=TEST_GASOLINE_MPG,
            fuel_grade=grade,
        )
    )

    return SavedVehicle(
        id=vehicle_id,
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Example",
            model="Test Vehicle",
            configuration="Standard",
            source="test",
            source_id="test-vehicle",
        ),
        specification=specification,
        specification_retrieved_at=AS_OF,
        saved_at=AS_OF,
    )


def make_body() -> dict[str, object]:
    return {
        "origin": {
            "display_name": "Los Angeles",
            "latitude": 34.0,
            "longitude": -118.0,
        },
        "destination": {
            "display_name": "Destination",
            "latitude": 34.1,
            "longitude": -118.1,
        },
    }


def make_client(
    *,
    grade: GasolineGrade = GasolineGrade.REGULAR,
    electric: bool = False,
    jurisdiction: PricingJurisdiction = PricingJurisdiction.CALIFORNIA,
    snapshots: dict[
        EiaGasolineRegion,
        EiaPricingSnapshot,
    ]
    | None = None,
    owned: bool = True,
) -> tuple[
    TestClient,
    FakeRoutes,
    FakeSnapshotReader,
    FakeJurisdictionResolver,
    SavedVehicleId,
]:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    preferences = Mock(spec=UserPreferencesRepository)
    preferences.get_preferences.return_value = UserPreferences(
        value_of_time_per_hour=Decimal(20),
        default_vehicle_id=vehicle_id,
    )

    vehicles = Mock(spec=SavedVehicleRepository)
    vehicles.get_vehicle.return_value = (
        make_vehicle(
            vehicle_id,
            grade=grade,
            electric=electric,
        )
        if owned
        else None
    )

    routes = FakeRoutes()
    reader = FakeSnapshotReader(snapshots or {})
    jurisdiction_resolver = FakeJurisdictionResolver(jurisdiction)

    price_provider = PostgresEiaGasolinePriceProvider(
        repository=reader,
    )

    service = build_terrain_v2_evaluation_service(
        preferences_repository=cast(
            UserPreferencesRepository,
            preferences,
        ),
        saved_vehicle_repository=cast(
            SavedVehicleRepository,
            vehicles,
        ),
        route_provider=cast(RouteProvider, routes),
        gasoline_price_provider=price_provider,
        gasoline_jurisdiction_resolver=cast(
            PricingJurisdictionResolver,
            jurisdiction_resolver,
        ),
        pricing_clock=lambda: AS_OF,
    )

    app = create_app()

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)
    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = lambda: service

    return (
        TestClient(app),
        routes,
        reader,
        jurisdiction_resolver,
        vehicle_id,
    )


def energy_cost(response: dict[str, object]) -> Decimal:
    evaluations = response["route_evaluations"]
    assert isinstance(evaluations, list)

    first = evaluations[0]
    assert isinstance(first, dict)

    estimate = first["energy_estimate"]
    assert isinstance(estimate, dict)

    return Decimal(str(estimate["cost"]))


def expected_gasoline_cost(price_per_gallon: str) -> Decimal:
    """Expected cost from exact route meters, saved MPG, and price."""
    distance_miles = Decimal(ROUTE_DISTANCE_METERS) / METERS_PER_MILE
    gallons = distance_miles / TEST_GASOLINE_MPG
    return gallons * Decimal(price_per_gallon)


def expected_electric_cost(price_per_kwh: str) -> Decimal:
    """Expected cost from exact route meters and energy efficiency."""
    distance_miles = Decimal(ROUTE_DISTANCE_METERS) / METERS_PER_MILE
    kilowatt_hours = distance_miles * TEST_ELECTRIC_KWH_PER_MILE
    return kilowatt_hours * Decimal(price_per_kwh)


def assert_cost_matches(
    response: dict[str, object],
    expected_cost: Decimal,
) -> None:
    """Allow only sub-tenth-cent numeric representation differences."""
    actual = energy_cost(response)
    assert abs(actual - expected_cost) <= COST_TOLERANCE


def california_snapshot() -> EiaPricingSnapshot:
    return make_snapshot(
        EIA_CALIFORNIA_REGION,
        regular="6.00",
        midgrade="6.50",
        premium="7.00",
    )


def national_snapshot() -> EiaPricingSnapshot:
    return make_snapshot(
        EIA_US_REGION,
        regular="4.00",
        midgrade="4.50",
        premium="5.00",
    )


def test_automatic_california_price_end_to_end() -> None:
    client, routes, reader, resolver, _ = make_client(
        snapshots={
            EIA_CALIFORNIA_REGION: california_snapshot(),
            EIA_US_REGION: national_snapshot(),
        }
    )

    with client:
        response = client.post(_PATH, json=make_body())

    assert response.status_code == 200
    assert_cost_matches(
        response.json(),
        expected_gasoline_cost("6.00"),
    )
    assert reader.reads == [EIA_CALIFORNIA_REGION]
    assert len(resolver.calls) == 1
    assert len(routes.calls) == 1


def test_missing_california_price_uses_national_fallback() -> None:
    client, routes, reader, _, _ = make_client(snapshots={EIA_US_REGION: national_snapshot()})

    with client:
        response = client.post(_PATH, json=make_body())

    assert response.status_code == 200
    assert_cost_matches(
        response.json(),
        expected_gasoline_cost("4.00"),
    )
    assert reader.reads == [
        EIA_CALIFORNIA_REGION,
        EIA_US_REGION,
    ]
    assert len(routes.calls) == 1


def test_premium_vehicle_uses_premium_price() -> None:
    client, _, reader, _, _ = make_client(
        grade=GasolineGrade.PREMIUM,
        snapshots={
            EIA_CALIFORNIA_REGION: california_snapshot(),
        },
    )

    with client:
        response = client.post(_PATH, json=make_body())

    assert response.status_code == 200
    assert_cost_matches(
        response.json(),
        expected_gasoline_cost("7.00"),
    )
    assert reader.reads == [EIA_CALIFORNIA_REGION]


def test_manual_price_bypasses_eia_and_geography() -> None:
    client, routes, reader, resolver, _ = make_client()

    body = make_body()
    body["gasoline"] = {
        "fuel_price_per_gallon": "3.00",
    }

    with client:
        response = client.post(_PATH, json=body)

    assert response.status_code == 200
    assert_cost_matches(
        response.json(),
        expected_gasoline_cost("3.00"),
    )
    assert reader.reads == []
    assert resolver.calls == []
    assert len(routes.calls) == 1


def test_bev_with_electricity_never_reads_eia() -> None:
    client, routes, reader, resolver, _ = make_client(
        electric=True,
    )

    body = make_body()
    body["electricity"] = {
        "price_per_kilowatt_hour": "0.25",
    }

    with client:
        response = client.post(_PATH, json=body)

    assert response.status_code == 200
    assert_cost_matches(
        response.json(),
        expected_electric_cost("0.25"),
    )
    assert reader.reads == []
    assert resolver.calls == []
    assert len(routes.calls) == 1


def test_bev_without_electricity_rejected_before_routing() -> None:
    client, routes, reader, resolver, _ = make_client(
        electric=True,
    )

    with client:
        response = client.post(_PATH, json=make_body())

    assert response.status_code == 409
    assert response.json()["code"] == "energy_input_mismatch"
    assert routes.calls == []
    assert reader.reads == []
    assert resolver.calls == []


def test_unowned_vehicle_rejected_before_pricing() -> None:
    client, routes, reader, resolver, vehicle_id = make_client(
        owned=False,
    )

    body = make_body()
    body["saved_vehicle_id"] = str(vehicle_id.value)

    with client:
        response = client.post(_PATH, json=body)

    assert response.status_code == 404
    assert response.json()["code"] == "saved_vehicle_not_found"
    assert routes.calls == []
    assert reader.reads == []
    assert resolver.calls == []


def test_stale_price_returns_safe_error() -> None:
    stale = make_snapshot(
        EIA_CALIFORNIA_REGION,
        regular="6.00",
        midgrade="6.50",
        premium="7.00",
        observed_on=date(2026, 9, 1),
    )

    client, routes, reader, _, _ = make_client(
        snapshots={
            EIA_CALIFORNIA_REGION: stale,
        },
    )

    with client:
        response = client.post(_PATH, json=make_body())

    assert response.status_code == 503
    assert response.json()["code"] == "gasoline_price_stale"
    assert len(reader.reads) == 2
    assert routes.calls == []


def test_non_california_us_reads_only_national() -> None:
    client, routes, reader, _, _ = make_client(
        jurisdiction=PricingJurisdiction.OTHER_US,
        snapshots={
            EIA_CALIFORNIA_REGION: california_snapshot(),
            EIA_US_REGION: national_snapshot(),
        },
    )

    with client:
        response = client.post(_PATH, json=make_body())

    assert response.status_code == 200
    assert_cost_matches(
        response.json(),
        expected_gasoline_cost("4.00"),
    )
    assert reader.reads == [EIA_US_REGION]
    assert len(routes.calls) == 1
