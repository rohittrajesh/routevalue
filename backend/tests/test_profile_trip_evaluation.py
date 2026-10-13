"""Application tests for authenticated profile-driven trip evaluation."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from routevalue.application.gasoline_evaluation import (
    GasolineEvaluationContext,
    UnsupportedVehicleEnergyTypeError,
)
from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteGeometry,
    RoutePoint,
    RouteSearchRequest,
    VehicleCatalogConfiguration,
)
from routevalue.application.ports import EnergyCostEstimator
from routevalue.application.preferences import UserPreferences
from routevalue.application.profile_resolution import (
    ProfileResolutionError,
    ProfileResolutionFailureReason,
    ProfileResolutionService,
)
from routevalue.application.profile_trip_evaluation import (
    ProfileDrivenTripEvaluationService,
)
from routevalue.application.saved_vehicles import (
    SavedVehicle,
    SavedVehicleSnapshot,
)
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    DecisionReason,
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolinePriceSource,
    GasolineVehicleSpecification,
    IneligibilityReason,
    RouteCandidate,
    VehicleEnergySpecification,
)
from routevalue.infrastructure.energy.gasoline import (
    GasolineEnergyCostEstimator,
)


class FakePreferencesRepository:
    """Read configured preferences without allowing writes."""

    def __init__(
        self,
        preferences: dict[UserId, UserPreferences],
    ) -> None:
        self.preferences = preferences

    def get_preferences(
        self,
        user_id: UserId,
    ) -> UserPreferences:
        return self.preferences.get(user_id, UserPreferences())

    def save_preferences(
        self,
        user_id: UserId,
        preferences: UserPreferences,
    ) -> UserPreferences:
        raise AssertionError("evaluation must not modify preferences")


class FakeSavedVehicleRepository:
    """Scope saved-vehicle retrieval to its authenticated owner."""

    def __init__(
        self,
        vehicles: dict[
            tuple[UserId, SavedVehicleId],
            SavedVehicle,
        ],
    ) -> None:
        self.vehicles = vehicles
        self.get_calls: list[tuple[UserId, SavedVehicleId]] = []

    def get_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> SavedVehicle | None:
        self.get_calls.append((user_id, vehicle_id))
        return self.vehicles.get((user_id, vehicle_id))

    def list_vehicles(
        self,
        user_id: UserId,
    ) -> Sequence[SavedVehicle]:
        raise AssertionError("evaluation must not list vehicles")

    def create_vehicle(
        self,
        user_id: UserId,
        snapshot: SavedVehicleSnapshot,
    ) -> SavedVehicle:
        raise AssertionError("evaluation must not save vehicles")

    def delete_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> bool:
        raise AssertionError("evaluation must not delete vehicles")


class RecordingRouteProvider:
    """Provide deterministic routes without external API calls."""

    def __init__(
        self,
        routes: Sequence[ProvidedRoute],
    ) -> None:
        self.routes = tuple(routes)
        self.requests: list[RouteSearchRequest] = []

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[ProvidedRoute]:
        self.requests.append(request)
        return self.routes


class RecordingEstimatorFactory:
    """Record the context passed to the existing gasoline estimator."""

    def __init__(self) -> None:
        self.contexts: list[GasolineEvaluationContext] = []

    def __call__(
        self,
        context: GasolineEvaluationContext,
    ) -> EnergyCostEstimator:
        self.contexts.append(context)

        return GasolineEnergyCostEstimator(
            vehicle=context.vehicle,
            fuel_price_quote=context.fuel_price_quote,
        )


def _vehicle(
    vehicle_id: SavedVehicleId,
    *,
    specification: VehicleEnergySpecification | None = None,
) -> SavedVehicle:
    if specification is None:
        specification = GasolineVehicleSpecification(
            combined_mpg=Decimal(25),
            fuel_grade=GasolineGrade.REGULAR,
        )

    return SavedVehicle(
        id=vehicle_id,
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Toyota",
            model="Camry",
            configuration="2.5L 4cyl CVT (FWD)",
            source="fueleconomy_gov",
            source_id="12345",
        ),
        specification=specification,
        specification_retrieved_at=datetime(2026, 10, 1, tzinfo=UTC),
        saved_at=datetime(2026, 10, 2, tzinfo=UTC),
    )


def _request() -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=ResolvedLocation(
            display_name="UC San Diego",
            latitude=32.8801,
            longitude=-117.2340,
        ),
        destination=ResolvedLocation(
            display_name="Downtown San Diego",
            latitude=32.7157,
            longitude=-117.1611,
        ),
    )


def _routes() -> tuple[ProvidedRoute, ...]:
    """Return a slower cheaper route and a faster costlier route."""

    return (
        ProvidedRoute(
            route=RouteCandidate(
                distance_meters=16_093,
                duration_seconds=1800,
                toll_cost=Decimal(0),
            )
        ),
        ProvidedRoute(
            route=RouteCandidate(
                distance_meters=32_187,
                duration_seconds=900,
                toll_cost=Decimal(0),
            )
        ),
    )


def _service(
    *,
    preferences: dict[UserId, UserPreferences],
    vehicles: dict[
        tuple[UserId, SavedVehicleId],
        SavedVehicle,
    ],
    routes: Sequence[ProvidedRoute],
) -> tuple[
    ProfileDrivenTripEvaluationService,
    RecordingRouteProvider,
    RecordingEstimatorFactory,
    FakeSavedVehicleRepository,
]:
    preferences_repository = FakePreferencesRepository(preferences)
    vehicle_repository = FakeSavedVehicleRepository(vehicles)
    profile_service = ProfileResolutionService(
        preferences_repository=preferences_repository,
        saved_vehicle_repository=vehicle_repository,
    )
    provider = RecordingRouteProvider(routes)
    factory = RecordingEstimatorFactory()

    service = ProfileDrivenTripEvaluationService(
        profile_resolution_service=profile_service,
        route_provider=provider,
        gasoline_estimator_factory=factory,
    )

    return service, provider, factory, vehicle_repository


def test_default_profile_drives_gasoline_evaluation() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, provider, factory, repository = _service(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(0),
                default_vehicle_id=vehicle_id,
            )
        },
        vehicles={(user_id, vehicle_id): _vehicle(vehicle_id)},
        routes=_routes(),
    )

    result = service.evaluate_trip(
        user_id,
        _request(),
        fuel_price_per_gallon=Decimal("4.59"),
    )

    assert result.decision.recommended_route == _routes()[0].route
    assert result.decision.candidate_count == 2
    assert result.decision.eligible_count == 2
    assert not result.decision.missing_data_present

    assert provider.requests == [_request()]
    assert repository.get_calls == [(user_id, vehicle_id)]

    assert len(factory.contexts) == 1
    context = factory.contexts[0]

    assert context.vehicle.fuel_efficiency_mpg == Decimal(25)
    assert context.vehicle.fuel_grade is GasolineGrade.REGULAR
    assert context.fuel_price_quote.fuel_grade is GasolineGrade.REGULAR
    assert context.fuel_price_quote.source is (GasolinePriceSource.USER_OVERRIDE)

    estimate = result.route_evaluations[0].energy_estimate

    assert estimate is not None

    expected_cost = Decimal(16_093) / Decimal("1609.344") / Decimal(25) * Decimal("4.59")

    assert estimate.cost == expected_cost


def test_stored_value_of_time_changes_route_recommendation() -> None:
    low_user = UserId(value=uuid4())
    high_user = UserId(value=uuid4())

    low_vehicle_id = SavedVehicleId(value=uuid4())
    high_vehicle_id = SavedVehicleId(value=uuid4())

    routes = _routes()

    service, provider, _, _ = _service(
        preferences={
            low_user: UserPreferences(
                value_of_time_per_hour=Decimal(0),
                default_vehicle_id=low_vehicle_id,
            ),
            high_user: UserPreferences(
                value_of_time_per_hour=Decimal(30),
                default_vehicle_id=high_vehicle_id,
            ),
        },
        vehicles={
            (low_user, low_vehicle_id): _vehicle(low_vehicle_id),
            (high_user, high_vehicle_id): _vehicle(high_vehicle_id),
        },
        routes=routes,
    )

    low_result = service.evaluate_trip(
        low_user,
        _request(),
        fuel_price_per_gallon=Decimal("4.50"),
    )

    high_result = service.evaluate_trip(
        high_user,
        _request(),
        fuel_price_per_gallon=Decimal("4.50"),
    )

    assert low_result.decision.recommended_route == routes[0].route
    assert low_result.decision.reason is (DecisionReason.CHEAPER_ROUTE_WORTH_EXTRA_TIME)

    assert high_result.decision.recommended_route == routes[1].route
    assert high_result.decision.reason is (DecisionReason.FASTER_ROUTE_WORTH_EXTRA_COST)

    assert not low_result.decision.numerical_tie
    assert not high_result.decision.numerical_tie
    assert provider.requests == [_request(), _request()]


def test_explicit_owned_vehicle_overrides_default() -> None:
    user_id = UserId(value=uuid4())

    default_id = SavedVehicleId(value=uuid4())
    selected_id = SavedVehicleId(value=uuid4())

    selected = _vehicle(
        selected_id,
        specification=GasolineVehicleSpecification(
            combined_mpg=Decimal("31.75"),
            fuel_grade=GasolineGrade.PREMIUM,
        ),
    )

    service, _, factory, repository = _service(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(20),
                default_vehicle_id=default_id,
            )
        },
        vehicles={
            (user_id, default_id): _vehicle(default_id),
            (user_id, selected_id): selected,
        },
        routes=_routes(),
    )

    result = service.evaluate_trip(
        user_id,
        _request(),
        fuel_price_per_gallon=Decimal("5.25"),
        requested_vehicle_id=selected_id,
    )

    assert result.decision.eligible_count == 2
    assert repository.get_calls == [(user_id, selected_id)]

    context = factory.contexts[0]

    assert context.vehicle.fuel_efficiency_mpg == Decimal("31.75")
    assert context.vehicle.fuel_grade is GasolineGrade.PREMIUM
    assert context.fuel_price_quote.fuel_grade is GasolineGrade.PREMIUM
    assert context.fuel_price_quote.price_per_gallon == Decimal("5.25")


@pytest.mark.parametrize(
    ("preferences", "expected_reason"),
    [
        (
            UserPreferences(),
            ProfileResolutionFailureReason.VALUE_OF_TIME_NOT_CONFIGURED,
        ),
        (
            UserPreferences(value_of_time_per_hour=Decimal(25)),
            ProfileResolutionFailureReason.DEFAULT_VEHICLE_NOT_CONFIGURED,
        ),
    ],
)
def test_incomplete_profile_fails_before_route_acquisition(
    preferences: UserPreferences,
    expected_reason: ProfileResolutionFailureReason,
) -> None:
    user_id = UserId(value=uuid4())

    service, provider, factory, _ = _service(
        preferences={user_id: preferences},
        vehicles={},
        routes=_routes(),
    )

    with pytest.raises(ProfileResolutionError) as error:
        service.evaluate_trip(
            user_id,
            _request(),
            fuel_price_per_gallon=Decimal("4.50"),
        )

    assert error.value.reason is expected_reason
    assert provider.requests == []
    assert factory.contexts == []


def test_foreign_explicit_vehicle_cannot_fall_back_to_default() -> None:
    user_id = UserId(value=uuid4())
    foreign_user = UserId(value=uuid4())

    default_id = SavedVehicleId(value=uuid4())
    foreign_id = SavedVehicleId(value=uuid4())

    service, provider, factory, repository = _service(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(25),
                default_vehicle_id=default_id,
            )
        },
        vehicles={
            (user_id, default_id): _vehicle(default_id),
            (foreign_user, foreign_id): _vehicle(foreign_id),
        },
        routes=_routes(),
    )

    with pytest.raises(ProfileResolutionError) as error:
        service.evaluate_trip(
            user_id,
            _request(),
            fuel_price_per_gallon=Decimal("4.50"),
            requested_vehicle_id=foreign_id,
        )

    assert error.value.reason is (ProfileResolutionFailureReason.SAVED_VEHICLE_NOT_FOUND)
    assert repository.get_calls == [(user_id, foreign_id)]
    assert provider.requests == []
    assert factory.contexts == []


def test_stale_default_fails_before_route_acquisition() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, provider, factory, _ = _service(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(25),
                default_vehicle_id=vehicle_id,
            )
        },
        vehicles={},
        routes=_routes(),
    )

    with pytest.raises(ProfileResolutionError) as error:
        service.evaluate_trip(
            user_id,
            _request(),
            fuel_price_per_gallon=Decimal("4.50"),
        )

    assert error.value.reason is (ProfileResolutionFailureReason.DEFAULT_VEHICLE_UNAVAILABLE)
    assert provider.requests == []
    assert factory.contexts == []


def test_bev_evaluation_is_deferred_until_m5() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    bev = _vehicle(
        vehicle_id,
        specification=ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal("0.285"),
        ),
    )

    service, provider, factory, _ = _service(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(25),
                default_vehicle_id=vehicle_id,
            )
        },
        vehicles={(user_id, vehicle_id): bev},
        routes=_routes(),
    )

    with pytest.raises(UnsupportedVehicleEnergyTypeError):
        service.evaluate_trip(
            user_id,
            _request(),
            fuel_price_per_gallon=Decimal("4.50"),
        )

    assert provider.requests == []
    assert factory.contexts == []


def test_missing_toll_preserves_eligibility_and_geometry() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    geometry = RouteGeometry(
        points=(
            RoutePoint(latitude=32.8801, longitude=-117.2340),
            RoutePoint(latitude=32.7157, longitude=-117.1611),
        )
    )

    missing_toll = ProvidedRoute(
        route=RouteCandidate(
            distance_meters=10_000,
            duration_seconds=700,
            toll_cost=None,
        ),
        geometry=geometry,
    )

    valid_route = _routes()[0]

    service, _, _, _ = _service(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(25),
                default_vehicle_id=vehicle_id,
            )
        },
        vehicles={(user_id, vehicle_id): _vehicle(vehicle_id)},
        routes=(missing_toll, valid_route),
    )

    result = service.evaluate_trip(
        user_id,
        _request(),
        fuel_price_per_gallon=Decimal("4.50"),
    )

    assert result.route_evaluations[0].geometry == geometry

    assert result.route_evaluations[0].eligibility.reason is (IneligibilityReason.MISSING_TOLL_COST)

    assert result.route_evaluations[0].cost_breakdown is None
    assert result.route_evaluations[1].eligibility.eligible

    assert result.decision.recommended_route == valid_route.route
    assert result.decision.candidate_count == 2
    assert result.decision.eligible_count == 1
    assert result.decision.missing_data_present


def test_no_routes_preserves_existing_empty_decision() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, provider, _, _ = _service(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(25),
                default_vehicle_id=vehicle_id,
            )
        },
        vehicles={(user_id, vehicle_id): _vehicle(vehicle_id)},
        routes=(),
    )

    result = service.evaluate_trip(
        user_id,
        _request(),
        fuel_price_per_gallon=Decimal("4.50"),
    )

    assert result.route_evaluations == ()
    assert result.decision.recommended_route is None
    assert result.decision.candidate_count == 0
    assert result.decision.eligible_count == 0
    assert not result.decision.missing_data_present

    assert provider.requests == [_request()]


def test_each_request_gets_its_own_pricing_context() -> None:
    user_id = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, provider, factory, _ = _service(
        preferences={
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(10),
                default_vehicle_id=vehicle_id,
            )
        },
        vehicles={(user_id, vehicle_id): _vehicle(vehicle_id)},
        routes=_routes(),
    )

    first = service.evaluate_trip(
        user_id,
        _request(),
        fuel_price_per_gallon=Decimal("4.00"),
    )

    second = service.evaluate_trip(
        user_id,
        _request(),
        fuel_price_per_gallon=Decimal("8.00"),
    )

    first_estimate = first.route_evaluations[0].energy_estimate
    second_estimate = second.route_evaluations[0].energy_estimate

    assert first_estimate is not None
    assert second_estimate is not None
    assert second_estimate.cost == first_estimate.cost * 2

    assert [context.fuel_price_quote.price_per_gallon for context in factory.contexts] == [
        Decimal("4.00"),
        Decimal("8.00"),
    ]

    assert len(provider.requests) == 2
