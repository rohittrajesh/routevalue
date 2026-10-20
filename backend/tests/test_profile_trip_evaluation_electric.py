"""Application tests for dual-powertrain profile-driven evaluation."""

from collections.abc import Sequence
from dataclasses import replace as replace_preferences
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from routevalue.application.electric_evaluation import (
    ElectricEvaluationContext,
)
from routevalue.application.gasoline_evaluation import (
    GasolineEvaluationContext,
)
from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteSearchRequest,
    VehicleCatalogConfiguration,
)
from routevalue.application.ports import EnergyCostEstimator
from routevalue.application.preferences import UserPreferences, UserPreferencesPatch
from routevalue.application.profile_resolution import (
    ProfileResolutionError,
    ProfileResolutionFailureReason,
    ProfileResolutionService,
)
from routevalue.application.profile_trip_evaluation import (
    EnergyInputMismatchError,
    ProfileDrivenTripEvaluationService,
)
from routevalue.application.saved_vehicles import (
    SavedVehicle,
    SavedVehicleSnapshot,
)
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    DecisionReason,
    ElectricConsumption,
    ElectricVehicleSpecification,
    GasolineConsumption,
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
    VehicleEnergySpecification,
)
from routevalue.infrastructure.energy.electric import (
    ElectricEnergyCostEstimator,
)
from routevalue.infrastructure.energy.gasoline import (
    GasolineEnergyCostEstimator,
)


class FakePreferencesRepository:
    def __init__(self, values: dict[UserId, UserPreferences]) -> None:
        self.values = values

    def get_preferences(self, user_id: UserId) -> UserPreferences:
        return self.values.get(user_id, UserPreferences())

    def update_preferences(self, user_id: UserId, changes: UserPreferencesPatch) -> UserPreferences:
        current = self.get_preferences(user_id)
        updated = replace_preferences(current, **changes)
        if updated == current:
            return current
        return self.save_preferences(user_id, updated)

    def save_preferences(
        self,
        user_id: UserId,
        preferences: UserPreferences,
    ) -> UserPreferences:
        raise AssertionError("evaluation must not save preferences")


class FakeSavedVehicleRepository:
    def __init__(
        self,
        vehicles: dict[tuple[UserId, SavedVehicleId], SavedVehicle],
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


class FakeRouteProvider:
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
                    distance_meters=201_168,
                    duration_seconds=3600,
                    toll_cost=Decimal("4.00"),
                )
            ),
        )


def _gasoline_factory(
    context: GasolineEvaluationContext,
) -> EnergyCostEstimator:
    return GasolineEnergyCostEstimator(
        vehicle=context.vehicle,
        fuel_price_quote=context.fuel_price_quote,
    )


def _electric_factory(
    context: ElectricEvaluationContext,
) -> EnergyCostEstimator:
    return ElectricEnergyCostEstimator(
        vehicle=context.vehicle,
        electricity_price_quote=context.electricity_price_quote,
    )


def _vehicle(
    vehicle_id: SavedVehicleId,
    specification: VehicleEnergySpecification,
) -> SavedVehicle:
    return SavedVehicle(
        id=vehicle_id,
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Hyundai",
            model="Ioniq 5",
            configuration="Long Range RWD",
            source="fueleconomy_gov",
            source_id="12345",
        ),
        specification=specification,
        specification_retrieved_at=datetime(2026, 10, 1, tzinfo=UTC),
        saved_at=datetime(2026, 10, 2, tzinfo=UTC),
    )


def _bev_specification() -> ElectricVehicleSpecification:
    return ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.285"),
    )


def _gasoline_specification() -> GasolineVehicleSpecification:
    return GasolineVehicleSpecification(
        combined_mpg=Decimal(25),
        fuel_grade=GasolineGrade.REGULAR,
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
            latitude=32.72,
            longitude=-117.16,
        ),
    )


def _service(
    user_id: UserId,
    vehicles: dict[tuple[UserId, SavedVehicleId], SavedVehicle],
    default_vehicle_id: SavedVehicleId,
    *,
    with_electric_factory: bool = True,
) -> tuple[
    ProfileDrivenTripEvaluationService,
    FakeRouteProvider,
    FakeSavedVehicleRepository,
]:
    preferences = FakePreferencesRepository(
        {
            user_id: UserPreferences(
                value_of_time_per_hour=Decimal(20),
                default_vehicle_id=default_vehicle_id,
            )
        }
    )
    vehicle_repository = FakeSavedVehicleRepository(vehicles)
    routes = FakeRouteProvider()

    profile_service = ProfileResolutionService(
        preferences_repository=preferences,
        saved_vehicle_repository=vehicle_repository,
    )

    service = ProfileDrivenTripEvaluationService(
        profile_resolution_service=profile_service,
        route_provider=routes,
        gasoline_estimator_factory=_gasoline_factory,
        electric_estimator_factory=(_electric_factory if with_electric_factory else None),
    )

    return service, routes, vehicle_repository


def test_default_bev_evaluates_using_saved_efficiency() -> None:
    user = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, routes, repository = _service(
        user,
        {(user, vehicle_id): _vehicle(vehicle_id, _bev_specification())},
        vehicle_id,
    )

    result = service.evaluate_trip(
        user,
        _request(),
        price_per_kilowatt_hour=Decimal("0.31"),
    )

    estimate = result.route_evaluations[0].energy_estimate

    assert estimate is not None
    assert isinstance(estimate.consumption, ElectricConsumption)
    assert estimate.consumption.kilowatt_hours == Decimal("35.625")
    assert estimate.cost == Decimal("11.04375")

    assert result.decision.reason is DecisionReason.ONLY_ELIGIBLE_ROUTE
    assert result.decision.missing_data_present is False
    assert repository.get_calls == [(user, vehicle_id)]
    assert len(routes.calls) == 1


def test_explicit_bev_overrides_gasoline_default() -> None:
    user = UserId(value=uuid4())
    gasoline_id = SavedVehicleId(value=uuid4())
    bev_id = SavedVehicleId(value=uuid4())

    service, routes, repository = _service(
        user,
        {
            (user, gasoline_id): _vehicle(gasoline_id, _gasoline_specification()),
            (user, bev_id): _vehicle(bev_id, _bev_specification()),
        },
        gasoline_id,
    )

    result = service.evaluate_trip(
        user,
        _request(),
        price_per_kilowatt_hour=Decimal("0.31"),
        requested_vehicle_id=bev_id,
    )

    estimate = result.route_evaluations[0].energy_estimate

    assert estimate is not None
    assert isinstance(estimate.consumption, ElectricConsumption)
    assert repository.get_calls == [(user, bev_id)]
    assert len(routes.calls) == 1


def test_gasoline_evaluation_still_works() -> None:
    user = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, routes, _ = _service(
        user,
        {(user, vehicle_id): _vehicle(vehicle_id, _gasoline_specification())},
        vehicle_id,
    )

    result = service.evaluate_trip(
        user,
        _request(),
        fuel_price_per_gallon=Decimal("4.50"),
    )

    estimate = result.route_evaluations[0].energy_estimate

    assert estimate is not None
    assert isinstance(estimate.consumption, GasolineConsumption)
    assert estimate.consumption.gallons == Decimal(5)
    assert estimate.cost == Decimal("22.50")
    assert len(routes.calls) == 1


@pytest.mark.parametrize(
    ("specification", "gas_price", "electric_price"),
    [
        (
            ElectricVehicleSpecification(combined_kwh_per_mile=Decimal("0.285")),
            Decimal("4.50"),
            None,
        ),
        (
            GasolineVehicleSpecification(
                combined_mpg=Decimal(25),
                fuel_grade=GasolineGrade.REGULAR,
            ),
            None,
            Decimal("0.31"),
        ),
    ],
)
def test_mismatched_energy_input_fails_before_routing(
    specification: VehicleEnergySpecification,
    gas_price: Decimal | None,
    electric_price: Decimal | None,
) -> None:
    user = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, routes, _ = _service(
        user,
        {(user, vehicle_id): _vehicle(vehicle_id, specification)},
        vehicle_id,
    )

    with pytest.raises(EnergyInputMismatchError):
        service.evaluate_trip(
            user,
            _request(),
            fuel_price_per_gallon=gas_price,
            price_per_kilowatt_hour=electric_price,
        )

    assert routes.calls == []


@pytest.mark.parametrize(
    ("gas_price", "electric_price"),
    [
        (None, None),
        (Decimal("4.50"), Decimal("0.31")),
    ],
)
def test_exactly_one_energy_price_is_required(
    gas_price: Decimal | None,
    electric_price: Decimal | None,
) -> None:
    user = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, routes, _ = _service(
        user,
        {(user, vehicle_id): _vehicle(vehicle_id, _bev_specification())},
        vehicle_id,
    )

    with pytest.raises(ValueError, match="exactly one energy price"):
        service.evaluate_trip(
            user,
            _request(),
            fuel_price_per_gallon=gas_price,
            price_per_kilowatt_hour=electric_price,
        )

    assert routes.calls == []


def test_zero_electricity_price_is_valid() -> None:
    user = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, _, _ = _service(
        user,
        {(user, vehicle_id): _vehicle(vehicle_id, _bev_specification())},
        vehicle_id,
    )

    result = service.evaluate_trip(
        user,
        _request(),
        price_per_kilowatt_hour=Decimal(0),
    )

    estimate = result.route_evaluations[0].energy_estimate

    assert estimate is not None
    assert estimate.cost == Decimal(0)
    assert isinstance(estimate.consumption, ElectricConsumption)
    assert estimate.consumption.kilowatt_hours > 0


def test_foreign_bev_id_does_not_bypass_ownership() -> None:
    user = UserId(value=uuid4())
    foreign_user = UserId(value=uuid4())
    own_id = SavedVehicleId(value=uuid4())
    foreign_id = SavedVehicleId(value=uuid4())

    service, routes, repository = _service(
        user,
        {
            (user, own_id): _vehicle(own_id, _gasoline_specification()),
            (foreign_user, foreign_id): _vehicle(foreign_id, _bev_specification()),
        },
        own_id,
    )

    with pytest.raises(ProfileResolutionError) as error:
        service.evaluate_trip(
            user,
            _request(),
            price_per_kilowatt_hour=Decimal("0.31"),
            requested_vehicle_id=foreign_id,
        )

    assert error.value.reason is (ProfileResolutionFailureReason.SAVED_VEHICLE_NOT_FOUND)
    assert repository.get_calls == [(user, foreign_id)]
    assert routes.calls == []


def test_missing_electric_factory_fails_before_routing() -> None:
    user = UserId(value=uuid4())
    vehicle_id = SavedVehicleId(value=uuid4())

    service, routes, _ = _service(
        user,
        {(user, vehicle_id): _vehicle(vehicle_id, _bev_specification())},
        vehicle_id,
        with_electric_factory=False,
    )

    with pytest.raises(RuntimeError, match="not configured"):
        service.evaluate_trip(
            user,
            _request(),
            price_per_kilowatt_hour=Decimal("0.31"),
        )

    assert routes.calls == []
