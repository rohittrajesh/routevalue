"""Tests for provider-neutral user-owned saved vehicles."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest

from routevalue.application.models import (
    VehicleCatalogConfiguration,
    VehicleSpecificationLookupResult,
    VehicleSpecificationUnavailableReason,
)
from routevalue.application.ports import (
    SavedVehicleRepository,
    VehicleSpecificationProvider,
)
from routevalue.application.saved_vehicles import (
    SavedVehicle,
    SavedVehicleCreationResult,
    SavedVehicleSnapshot,
)
from routevalue.application.user_saved_vehicles import (
    UserSavedVehiclesService,
)
from routevalue.domain.identity import (
    SavedVehicleId,
    UserId,
)
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
)
from routevalue.domain.vehicle_mass import VehicleMass, VehicleMassSource

_RETRIEVED_AT = datetime(
    2026,
    10,
    7,
    18,
    30,
    tzinfo=UTC,
)

_SAVED_AT = datetime(
    2026,
    10,
    7,
    18,
    31,
    tzinfo=UTC,
)


def _configuration() -> VehicleCatalogConfiguration:
    return VehicleCatalogConfiguration(
        year=2025,
        make="Toyota",
        model="Camry",
        configuration="2.5L 4cyl CVT (FWD)",
        source="fueleconomy_gov",
        source_id="12345",
    )


def _gasoline_specification() -> GasolineVehicleSpecification:
    return GasolineVehicleSpecification(
        combined_mpg=Decimal("32.125"),
        city_mpg=Decimal("28.5"),
        highway_mpg=Decimal("38.25"),
        fuel_grade=GasolineGrade.REGULAR,
    )


def _user_id() -> UserId:
    return UserId(value=uuid4())


class FakeSavedVehicleRepository:
    """In-memory ownership-scoped vehicle repository."""

    def __init__(self) -> None:
        self._vehicles: dict[
            tuple[UserId, SavedVehicleId],
            SavedVehicle,
        ] = {}

        self.list_requests: list[UserId] = []

        self.get_requests: list[tuple[UserId, SavedVehicleId]] = []

        self.create_requests: list[tuple[UserId, SavedVehicleSnapshot]] = []

        self.delete_requests: list[tuple[UserId, SavedVehicleId]] = []

    def list_vehicles(
        self,
        user_id: UserId,
    ) -> Sequence[SavedVehicle]:
        self.list_requests.append(user_id)

        return tuple(
            vehicle
            for (
                owner_id,
                _,
            ), vehicle in self._vehicles.items()
            if owner_id == user_id
        )

    def get_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> SavedVehicle | None:
        self.get_requests.append(
            (
                user_id,
                vehicle_id,
            )
        )

        return self._vehicles.get(
            (
                user_id,
                vehicle_id,
            )
        )

    def create_vehicle(
        self,
        user_id: UserId,
        snapshot: SavedVehicleSnapshot,
    ) -> SavedVehicle:
        self.create_requests.append(
            (
                user_id,
                snapshot,
            )
        )

        vehicle = SavedVehicle(
            id=SavedVehicleId(value=uuid4()),
            configuration=snapshot.configuration,
            specification=snapshot.specification,
            specification_retrieved_at=(snapshot.specification_retrieved_at),
            saved_at=_SAVED_AT,
        )

        self._vehicles[
            (
                user_id,
                vehicle.id,
            )
        ] = vehicle

        return vehicle

    def delete_vehicle(
        self,
        user_id: UserId,
        vehicle_id: SavedVehicleId,
    ) -> bool:
        self.delete_requests.append(
            (
                user_id,
                vehicle_id,
            )
        )

        return (
            self._vehicles.pop(
                (
                    user_id,
                    vehicle_id,
                ),
                None,
            )
            is not None
        )


class FakeVehicleSpecificationProvider:
    """Controlled provider for save-time catalog revalidation."""

    def __init__(
        self,
        *,
        configurations: Sequence[VehicleCatalogConfiguration],
        specification_result: (VehicleSpecificationLookupResult),
    ) -> None:
        self._configurations = tuple(configurations)
        self._specification_result = specification_result

        self.configuration_requests: list[tuple[int, str, str]] = []

        self.specification_requests: list[VehicleCatalogConfiguration] = []

    def list_years(self) -> Sequence[int]:
        return ()

    def list_makes(
        self,
        *,
        year: int,
    ) -> Sequence[str]:
        del year
        return ()

    def list_models(
        self,
        *,
        year: int,
        make: str,
    ) -> Sequence[str]:
        del year
        del make
        return ()

    def list_configurations(
        self,
        *,
        year: int,
        make: str,
        model: str,
    ) -> Sequence[VehicleCatalogConfiguration]:
        self.configuration_requests.append(
            (
                year,
                make,
                model,
            )
        )

        return self._configurations

    def get_specification(
        self,
        configuration: VehicleCatalogConfiguration,
    ) -> VehicleSpecificationLookupResult:
        self.specification_requests.append(configuration)

        return self._specification_result


def _available_provider() -> FakeVehicleSpecificationProvider:
    return FakeVehicleSpecificationProvider(
        configurations=(_configuration(),),
        specification_result=(
            VehicleSpecificationLookupResult(
                specification=(_gasoline_specification()),
                unavailable_reason=None,
            )
        ),
    )


def _service(
    repository: SavedVehicleRepository,
    provider: VehicleSpecificationProvider,
) -> UserSavedVehiclesService:
    return UserSavedVehiclesService(
        repository=repository,
        specification_provider=provider,
        clock=lambda: _RETRIEVED_AT,
    )


def test_saved_vehicle_id_requires_uuid() -> None:
    with pytest.raises(
        TypeError,
        match="SavedVehicleId must contain a UUID",
    ):
        SavedVehicleId(
            value=cast(
                UUID,
                "not-a-uuid",
            )
        )


def test_snapshot_preserves_gasoline_specification() -> None:
    snapshot = SavedVehicleSnapshot(
        configuration=_configuration(),
        specification=_gasoline_specification(),
        specification_retrieved_at=_RETRIEVED_AT,
    )

    assert snapshot.configuration == _configuration()
    assert snapshot.specification == _gasoline_specification()
    assert snapshot.specification_retrieved_at == _RETRIEVED_AT


def test_snapshot_accepts_electric_specification() -> None:
    specification = ElectricVehicleSpecification(
        combined_kwh_per_mile=Decimal("0.285"),
        city_kwh_per_mile=Decimal("0.250"),
        highway_kwh_per_mile=Decimal("0.320"),
    )

    snapshot = SavedVehicleSnapshot(
        configuration=_configuration(),
        specification=specification,
        specification_retrieved_at=_RETRIEVED_AT,
    )

    assert snapshot.specification == specification


def test_snapshot_rejects_naive_retrieval_time() -> None:
    with pytest.raises(
        ValueError,
        match=("specification_retrieved_at must be timezone-aware"),
    ):
        SavedVehicleSnapshot(
            configuration=_configuration(),
            specification=_gasoline_specification(),
            specification_retrieved_at=datetime(  # noqa: DTZ001
                2026,
                10,
                7,
                18,
                30,
            ),
        )


def test_saved_vehicle_rejects_naive_saved_at() -> None:
    with pytest.raises(
        ValueError,
        match="saved_at must be timezone-aware",
    ):
        SavedVehicle(
            id=SavedVehicleId(value=uuid4()),
            configuration=_configuration(),
            specification=_gasoline_specification(),
            specification_retrieved_at=_RETRIEVED_AT,
            saved_at=datetime(  # noqa: DTZ001
                2026,
                10,
                7,
                18,
                31,
            ),
        )


def test_creation_result_accepts_saved_vehicle() -> None:
    vehicle = SavedVehicle(
        id=SavedVehicleId(value=uuid4()),
        configuration=_configuration(),
        specification=_gasoline_specification(),
        specification_retrieved_at=_RETRIEVED_AT,
        saved_at=_SAVED_AT,
    )

    result = SavedVehicleCreationResult(
        saved_vehicle=vehicle,
        unavailable_reason=None,
    )

    assert result.saved_vehicle == vehicle
    assert result.unavailable_reason is None


def test_creation_result_accepts_unavailable_reason() -> None:
    result = SavedVehicleCreationResult(
        saved_vehicle=None,
        unavailable_reason=(VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN),
    )

    assert result.saved_vehicle is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN


def test_creation_result_rejects_missing_outcome() -> None:
    with pytest.raises(
        ValueError,
        match=("requires exactly one of saved_vehicle or unavailable_reason"),
    ):
        SavedVehicleCreationResult(
            saved_vehicle=None,
            unavailable_reason=None,
        )


def test_service_lists_only_requested_user_scope() -> None:
    repository = FakeSavedVehicleRepository()
    provider = _available_provider()
    service = _service(
        repository,
        provider,
    )

    user_id = _user_id()

    assert service.list_vehicles(user_id) == ()

    assert repository.list_requests == [user_id]


def test_service_gets_vehicle_with_owner_scope() -> None:
    repository = FakeSavedVehicleRepository()
    provider = _available_provider()
    service = _service(
        repository,
        provider,
    )

    user_id = _user_id()
    vehicle_id = SavedVehicleId(value=uuid4())

    assert (
        service.get_vehicle(
            user_id,
            vehicle_id,
        )
        is None
    )

    assert repository.get_requests == [
        (
            user_id,
            vehicle_id,
        )
    ]


def test_save_revalidates_catalog_and_persists_normalized_snapshot() -> None:
    repository = FakeSavedVehicleRepository()
    provider = _available_provider()

    service = _service(
        repository,
        provider,
    )

    user_id = _user_id()
    configuration = _configuration()

    result = service.save_catalog_vehicle(
        user_id,
        configuration,
    )

    assert provider.configuration_requests == [
        (
            configuration.year,
            configuration.make,
            configuration.model,
        )
    ]

    assert provider.specification_requests == [configuration]

    assert len(repository.create_requests) == 1

    created_user_id, snapshot = repository.create_requests[0]

    assert created_user_id == user_id
    assert snapshot.configuration == configuration
    assert snapshot.specification == _gasoline_specification()
    assert snapshot.specification_retrieved_at == _RETRIEVED_AT

    assert result.saved_vehicle is not None
    assert result.unavailable_reason is None


def test_save_rejects_configuration_not_present_in_provider_catalog() -> None:
    repository = FakeSavedVehicleRepository()

    provider = FakeVehicleSpecificationProvider(
        configurations=(),
        specification_result=(
            VehicleSpecificationLookupResult(
                specification=(_gasoline_specification()),
                unavailable_reason=None,
            )
        ),
    )

    service = _service(
        repository,
        provider,
    )

    result = service.save_catalog_vehicle(
        _user_id(),
        _configuration(),
    )

    assert result.saved_vehicle is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.NOT_FOUND

    assert provider.specification_requests == []
    assert repository.create_requests == []


def test_save_does_not_persist_unavailable_specification() -> None:
    repository = FakeSavedVehicleRepository()

    provider = FakeVehicleSpecificationProvider(
        configurations=(_configuration(),),
        specification_result=(
            VehicleSpecificationLookupResult(
                specification=None,
                unavailable_reason=(VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA),
            )
        ),
    )

    service = _service(
        repository,
        provider,
    )

    result = service.save_catalog_vehicle(
        _user_id(),
        _configuration(),
    )

    assert result.saved_vehicle is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA

    assert repository.create_requests == []


def test_service_deletes_vehicle_with_owner_scope() -> None:
    repository = FakeSavedVehicleRepository()
    provider = _available_provider()
    service = _service(
        repository,
        provider,
    )

    user_id = _user_id()
    vehicle_id = SavedVehicleId(value=uuid4())

    deleted = service.delete_vehicle(
        user_id,
        vehicle_id,
    )

    assert deleted is False

    assert repository.delete_requests == [
        (
            user_id,
            vehicle_id,
        )
    ]


@pytest.mark.parametrize("electric", [False, True])
@pytest.mark.parametrize("source", list(VehicleMassSource))
def test_catalog_save_never_imports_mass_but_preserves_efficiency(
    electric: bool,
    source: VehicleMassSource,
) -> None:
    specification = (
        ElectricVehicleSpecification(combined_kwh_per_mile=Decimal("0.285"))
        if electric
        else _gasoline_specification()
    )
    supplied = replace(
        specification,
        vehicle_mass=VehicleMass(
            kilograms=Decimal(1800), source=source, source_reference="Catalog fixture"
        ),
    )
    provider = FakeVehicleSpecificationProvider(
        configurations=(_configuration(),),
        specification_result=VehicleSpecificationLookupResult(
            specification=supplied, unavailable_reason=None
        ),
    )
    repository = FakeSavedVehicleRepository()
    result = _service(repository, provider).save_catalog_vehicle(_user_id(), _configuration())

    assert result.saved_vehicle is not None
    assert result.saved_vehicle.specification == specification
    assert repository.create_requests[0][1].specification.vehicle_mass is None
    assert supplied.vehicle_mass is not None
