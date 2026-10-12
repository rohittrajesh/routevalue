"""Authenticated HTTP-to-PostgreSQL integration for V2 saved vehicles."""

from collections.abc import Sequence
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine

from routevalue.api.authentication import (
    get_authentication_verifier,
)
from routevalue.api.saved_vehicles import (
    get_saved_vehicle_repository,
    get_vehicle_specification_provider,
)
from routevalue.api.user_identity import (
    get_user_identity_repository,
)
from routevalue.application.identity import (
    VerifiedExternalIdentity,
)
from routevalue.application.models import (
    VehicleCatalogConfiguration,
    VehicleSpecificationLookupResult,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolineVehicleSpecification,
)
from routevalue.infrastructure.persistence.saved_vehicles import (
    PostgresSavedVehicleRepository,
)
from routevalue.infrastructure.persistence.schema import (
    auth_identities,
    saved_vehicles,
    users,
)
from routevalue.infrastructure.persistence.user_identity import (
    PostgresUserIdentityRepository,
)
from routevalue.main import create_app


class AcceptingVerifier:
    """Return one deterministic authenticated external identity."""

    def __init__(
        self,
        identity: VerifiedExternalIdentity,
    ) -> None:
        self._identity = identity

    def verify_token(
        self,
        token: str,
    ) -> VerifiedExternalIdentity:
        assert token == "valid-token"
        return self._identity


class DeterministicVehicleProvider:
    """Provide one server-controlled gasoline vehicle."""

    def __init__(
        self,
        configuration: VehicleCatalogConfiguration,
    ) -> None:
        self._configuration = configuration

    def list_years(self) -> Sequence[int]:
        return (self._configuration.year,)

    def list_makes(
        self,
        *,
        year: int,
    ) -> Sequence[str]:
        if year == self._configuration.year:
            return (self._configuration.make,)

        return ()

    def list_models(
        self,
        *,
        year: int,
        make: str,
    ) -> Sequence[str]:
        if year == self._configuration.year and make == self._configuration.make:
            return (self._configuration.model,)

        return ()

    def list_configurations(
        self,
        *,
        year: int,
        make: str,
        model: str,
    ) -> Sequence[VehicleCatalogConfiguration]:
        if (
            year == self._configuration.year
            and make == self._configuration.make
            and model == self._configuration.model
        ):
            return (self._configuration,)

        return ()

    def get_specification(
        self,
        configuration: VehicleCatalogConfiguration,
    ) -> VehicleSpecificationLookupResult:
        assert configuration == self._configuration

        return VehicleSpecificationLookupResult(
            specification=(
                GasolineVehicleSpecification(
                    combined_mpg=Decimal("31.987654321"),
                    city_mpg=Decimal("28.125"),
                    highway_mpg=Decimal("37.875"),
                    fuel_grade=(GasolineGrade.REGULAR),
                )
            ),
            unavailable_reason=None,
        )


def test_authenticated_saved_vehicle_round_trip_through_postgres(
    postgres_engine: Engine,
) -> None:
    identity = VerifiedExternalIdentity(
        issuer=(f"https://auth-{uuid4().hex}.example.test"),
        subject=f"subject-{uuid4().hex}",
    )

    configuration = VehicleCatalogConfiguration(
        year=2025,
        make="Toyota",
        model="Camry",
        configuration="2.5L 4cyl CVT (FWD)",
        source="fueleconomy_gov",
        source_id="12345",
    )

    app = create_app()

    app.dependency_overrides[get_authentication_verifier] = lambda: AcceptingVerifier(identity)

    app.dependency_overrides[get_user_identity_repository] = lambda: PostgresUserIdentityRepository(
        engine=postgres_engine,
    )

    app.dependency_overrides[get_saved_vehicle_repository] = lambda: PostgresSavedVehicleRepository(
        engine=postgres_engine,
    )

    app.dependency_overrides[get_vehicle_specification_provider] = lambda: (
        DeterministicVehicleProvider(configuration)
    )

    headers = {
        "Authorization": "Bearer valid-token",
    }

    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/v2/vehicles",
                headers=headers,
                json={
                    "year": configuration.year,
                    "make": configuration.make,
                    "model": configuration.model,
                    "configuration": (configuration.configuration),
                    "source": configuration.source,
                    "source_id": (configuration.source_id),
                },
            )

            assert created.status_code == 201

            vehicle_id = created.json()["id"]

            listed = client.get(
                "/api/v2/vehicles",
                headers=headers,
            )

            assert listed.status_code == 200
            assert len(listed.json()["vehicles"]) == 1

            fetched = client.get(
                f"/api/v2/vehicles/{vehicle_id}",
                headers=headers,
            )

            assert fetched.status_code == 200
            assert fetched.json() == created.json()

            with postgres_engine.connect() as connection:
                user_id = connection.execute(
                    select(auth_identities.c.user_id).where(
                        auth_identities.c.issuer == identity.issuer,
                        auth_identities.c.subject == identity.subject,
                    )
                ).scalar_one()

                row = (
                    connection.execute(
                        select(saved_vehicles).where(saved_vehicles.c.id == vehicle_id)
                    )
                    .mappings()
                    .one()
                )

            assert row["user_id"] == user_id

            assert row["combined_mpg"] == Decimal("31.987654321")

            deleted = client.delete(
                f"/api/v2/vehicles/{vehicle_id}",
                headers=headers,
            )

            assert deleted.status_code == 204

            missing = client.get(
                f"/api/v2/vehicles/{vehicle_id}",
                headers=headers,
            )

            assert missing.status_code == 404

    finally:
        with postgres_engine.begin() as connection:
            user_id = connection.execute(
                select(auth_identities.c.user_id).where(
                    auth_identities.c.issuer == identity.issuer,
                    auth_identities.c.subject == identity.subject,
                )
            ).scalar_one_or_none()

            if user_id is not None:
                connection.execute(delete(users).where(users.c.id == user_id))
