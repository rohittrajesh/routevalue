"""Cross-user ownership and default-vehicle hardening for RouteValue V2."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.engine import Engine

from routevalue.api.authentication import (
    get_authentication_verifier,
)
from routevalue.api.preferences import (
    get_user_preferences_repository,
)
from routevalue.api.saved_vehicles import (
    get_saved_vehicle_repository,
    get_vehicle_specification_provider,
)
from routevalue.api.user_identity import (
    get_user_identity_repository,
)
from routevalue.application.identity import (
    InvalidAuthenticationError,
    VerifiedExternalIdentity,
)
from routevalue.application.models import (
    VehicleCatalogConfiguration,
    VehicleSpecificationLookupResult,
)
from routevalue.application.saved_vehicles import (
    SavedVehicleSnapshot,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolineVehicleSpecification,
)
from routevalue.infrastructure.persistence.saved_vehicles import (
    PostgresSavedVehicleRepository,
)
from routevalue.infrastructure.persistence.schema import (
    users,
)
from routevalue.infrastructure.persistence.user_identity import (
    PostgresUserIdentityRepository,
)
from routevalue.infrastructure.persistence.user_preferences import (
    PostgresUserPreferencesRepository,
)
from routevalue.main import create_app


class TokenMappingVerifier:
    """Resolve deterministic test bearer tokens to external identities."""

    def __init__(
        self,
        identities: dict[str, VerifiedExternalIdentity],
    ) -> None:
        self._identities = identities

    def verify_token(
        self,
        token: str,
    ) -> VerifiedExternalIdentity:
        identity = self._identities.get(token)

        if identity is None:
            raise InvalidAuthenticationError

        return identity


class UnusedVehicleProvider:
    """Provider that must not be used by ownership-only requests."""

    def list_years(self) -> Sequence[int]:
        raise AssertionError("vehicle provider should not be called")

    def list_makes(
        self,
        *,
        year: int,
    ) -> Sequence[str]:
        del year
        raise AssertionError("vehicle provider should not be called")

    def list_models(
        self,
        *,
        year: int,
        make: str,
    ) -> Sequence[str]:
        del year
        del make
        raise AssertionError("vehicle provider should not be called")

    def list_configurations(
        self,
        *,
        year: int,
        make: str,
        model: str,
    ) -> Sequence[VehicleCatalogConfiguration]:
        del year
        del make
        del model
        raise AssertionError("vehicle provider should not be called")

    def get_specification(
        self,
        configuration: VehicleCatalogConfiguration,
    ) -> VehicleSpecificationLookupResult:
        del configuration
        raise AssertionError("vehicle provider should not be called")


def _identity(
    label: str,
) -> VerifiedExternalIdentity:
    return VerifiedExternalIdentity(
        issuer=f"https://auth-{label}-{uuid4().hex}.example.test",
        subject=f"{label}-{uuid4().hex}",
    )


def _snapshot(
    source_id: str,
) -> SavedVehicleSnapshot:
    return SavedVehicleSnapshot(
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Toyota",
            model="Camry",
            configuration="2.5L 4cyl CVT (FWD)",
            source="fueleconomy_gov",
            source_id=source_id,
        ),
        specification=GasolineVehicleSpecification(
            combined_mpg=Decimal("32.125"),
            city_mpg=Decimal("28.5"),
            highway_mpg=Decimal("38.25"),
            fuel_grade=GasolineGrade.REGULAR,
        ),
        specification_retrieved_at=datetime(
            2026,
            10,
            12,
            20,
            0,
            tzinfo=UTC,
        ),
    )


def _not_found_body() -> dict[str, str]:
    return {
        "code": "saved_vehicle_not_found",
        "detail": "Saved vehicle was not found.",
    }


def test_foreign_and_missing_saved_vehicles_are_indistinguishable(
    postgres_engine: Engine,
) -> None:
    owner_identity = _identity("owner")
    other_identity = _identity("other")

    identity_repository = PostgresUserIdentityRepository(
        engine=postgres_engine,
    )
    vehicle_repository = PostgresSavedVehicleRepository(
        engine=postgres_engine,
    )

    owner = identity_repository.get_or_create_user_id(
        owner_identity,
    )
    other = identity_repository.get_or_create_user_id(
        other_identity,
    )

    vehicle = vehicle_repository.create_vehicle(
        owner,
        _snapshot("owner-vehicle"),
    )

    app = create_app()

    app.dependency_overrides[get_authentication_verifier] = lambda: TokenMappingVerifier(
        {
            "owner-token": owner_identity,
            "other-token": other_identity,
        }
    )

    app.dependency_overrides[get_user_identity_repository] = lambda: identity_repository

    app.dependency_overrides[get_saved_vehicle_repository] = lambda: vehicle_repository

    app.dependency_overrides[get_vehicle_specification_provider] = lambda: UnusedVehicleProvider()

    foreign_path = f"/api/v2/vehicles/{vehicle.id.value}"
    missing_path = f"/api/v2/vehicles/{uuid4()}"

    try:
        with TestClient(app) as client:
            foreign_get = client.get(
                foreign_path,
                headers={
                    "Authorization": "Bearer other-token",
                },
            )

            missing_get = client.get(
                missing_path,
                headers={
                    "Authorization": "Bearer other-token",
                },
            )

            assert foreign_get.status_code == 404
            assert missing_get.status_code == 404

            assert foreign_get.json() == _not_found_body()
            assert missing_get.json() == _not_found_body()

            foreign_delete = client.delete(
                foreign_path,
                headers={
                    "Authorization": "Bearer other-token",
                },
            )

            missing_delete = client.delete(
                missing_path,
                headers={
                    "Authorization": "Bearer other-token",
                },
            )

            assert foreign_delete.status_code == 404
            assert missing_delete.status_code == 404

            assert foreign_delete.json() == _not_found_body()

            assert missing_delete.json() == _not_found_body()

            owner_get = client.get(
                foreign_path,
                headers={
                    "Authorization": "Bearer owner-token",
                },
            )

            assert owner_get.status_code == 200

    finally:
        with postgres_engine.begin() as connection:
            connection.execute(
                delete(users).where(
                    users.c.id.in_(
                        [
                            owner.value,
                            other.value,
                        ]
                    )
                )
            )


def test_default_vehicle_cannot_cross_user_boundary_or_leak_existence(
    postgres_engine: Engine,
) -> None:
    owner_identity = _identity("owner")
    other_identity = _identity("other")

    identity_repository = PostgresUserIdentityRepository(
        engine=postgres_engine,
    )
    preferences_repository = PostgresUserPreferencesRepository(
        engine=postgres_engine,
    )
    vehicle_repository = PostgresSavedVehicleRepository(
        engine=postgres_engine,
    )

    owner = identity_repository.get_or_create_user_id(
        owner_identity,
    )
    other = identity_repository.get_or_create_user_id(
        other_identity,
    )

    owner_vehicle = vehicle_repository.create_vehicle(
        owner,
        _snapshot("owner-default"),
    )

    other_vehicle = vehicle_repository.create_vehicle(
        other,
        _snapshot("foreign-default"),
    )

    app = create_app()

    app.dependency_overrides[get_authentication_verifier] = lambda: TokenMappingVerifier(
        {
            "owner-token": owner_identity,
            "other-token": other_identity,
        }
    )

    app.dependency_overrides[get_user_identity_repository] = lambda: identity_repository

    app.dependency_overrides[get_user_preferences_repository] = lambda: preferences_repository

    app.dependency_overrides[get_saved_vehicle_repository] = lambda: vehicle_repository

    app.dependency_overrides[get_vehicle_specification_provider] = lambda: UnusedVehicleProvider()

    owner_headers = {
        "Authorization": "Bearer owner-token",
    }

    try:
        with TestClient(app) as client:
            initial_update = client.patch(
                "/api/v2/preferences",
                headers=owner_headers,
                json={
                    "value_of_time_per_hour": "37.50",
                    "default_vehicle_id": (str(owner_vehicle.id.value)),
                },
            )

            assert initial_update.status_code == 200

            assert initial_update.json() == {
                "value_of_time_per_hour": "37.50",
                "default_vehicle_id": (str(owner_vehicle.id.value)),
            }

            foreign_default = client.patch(
                "/api/v2/preferences",
                headers=owner_headers,
                json={
                    "default_vehicle_id": (str(other_vehicle.id.value)),
                },
            )

            missing_default = client.patch(
                "/api/v2/preferences",
                headers=owner_headers,
                json={
                    "default_vehicle_id": str(uuid4()),
                },
            )

            assert foreign_default.status_code == 404
            assert missing_default.status_code == 404

            assert foreign_default.json() == _not_found_body()

            assert missing_default.json() == _not_found_body()

            unchanged = client.get(
                "/api/v2/preferences",
                headers=owner_headers,
            )

            assert unchanged.status_code == 200

            assert unchanged.json() == {
                "value_of_time_per_hour": "37.50",
                "default_vehicle_id": (str(owner_vehicle.id.value)),
            }

            deleted = client.delete(
                (f"/api/v2/vehicles/{owner_vehicle.id.value}"),
                headers=owner_headers,
            )

            assert deleted.status_code == 204

            after_delete = client.get(
                "/api/v2/preferences",
                headers=owner_headers,
            )

            assert after_delete.status_code == 200

            assert after_delete.json() == {
                "value_of_time_per_hour": "37.50",
                "default_vehicle_id": None,
            }

            foreign_vehicle_still_exists = client.get(
                (f"/api/v2/vehicles/{other_vehicle.id.value}"),
                headers={
                    "Authorization": ("Bearer other-token"),
                },
            )

            assert foreign_vehicle_still_exists.status_code == 200

    finally:
        with postgres_engine.begin() as connection:
            connection.execute(
                delete(users).where(
                    users.c.id.in_(
                        [
                            owner.value,
                            other.value,
                        ]
                    )
                )
            )
