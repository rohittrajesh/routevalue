"""HTTP-to-PostgreSQL integration for authenticated user resolution."""

from concurrent.futures import ThreadPoolExecutor
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine

from routevalue.api.authentication import (
    get_authentication_verifier,
)
from routevalue.api.user_identity import (
    get_authenticated_user,
    get_user_identity_repository,
)
from routevalue.application.identity import (
    AuthenticatedUser,
    VerifiedExternalIdentity,
)
from routevalue.application.user_identity import (
    AuthenticatedUserResolver,
)
from routevalue.infrastructure.persistence.schema import (
    auth_identities,
    users,
)
from routevalue.infrastructure.persistence.user_identity import (
    PostgresUserIdentityRepository,
)


class AcceptingVerifier:
    """Return one deterministic verified identity."""

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


def _identity() -> VerifiedExternalIdentity:
    return VerifiedExternalIdentity(
        issuer=(f"https://auth-{uuid4().hex}.example.test"),
        subject=f"subject-{uuid4().hex}",
    )


def _delete_identity_user(
    engine: Engine,
    identity: VerifiedExternalIdentity,
) -> None:
    with engine.begin() as connection:
        user_id = connection.execute(
            select(auth_identities.c.user_id).where(
                auth_identities.c.issuer == identity.issuer,
                auth_identities.c.subject == identity.subject,
            )
        ).scalar_one_or_none()

        if user_id is not None:
            connection.execute(delete(users).where(users.c.id == user_id))


def test_authenticated_http_requests_reuse_persisted_user(
    postgres_engine: Engine,
) -> None:
    identity = _identity()

    repository = PostgresUserIdentityRepository(
        engine=postgres_engine,
    )

    app = FastAPI()

    app.dependency_overrides[get_authentication_verifier] = lambda: AcceptingVerifier(identity)

    app.dependency_overrides[get_user_identity_repository] = lambda: repository

    @app.get("/protected-user")
    def protected_user(
        user: Annotated[
            AuthenticatedUser,
            Depends(get_authenticated_user),
        ],
    ) -> dict[str, str]:
        return {
            "user_id": str(user.user_id.value),
        }

    client = TestClient(app)

    try:
        first = client.get(
            "/protected-user",
            headers={
                "Authorization": ("Bearer valid-token"),
            },
        )

        second = client.get(
            "/protected-user",
            headers={
                "Authorization": ("Bearer valid-token"),
            },
        )

        assert first.status_code == 200
        assert second.status_code == 200

        first_id = UUID(first.json()["user_id"])

        second_id = UUID(second.json()["user_id"])

        assert first_id == second_id

        with postgres_engine.connect() as connection:
            mapping_count = connection.execute(
                select(func.count())
                .select_from(auth_identities)
                .where(
                    auth_identities.c.issuer == identity.issuer,
                    auth_identities.c.subject == identity.subject,
                )
            ).scalar_one()

        assert mapping_count == 1

    finally:
        _delete_identity_user(
            postgres_engine,
            identity,
        )


def test_concurrent_application_resolution_converges_on_one_user(
    postgres_engine: Engine,
) -> None:
    identity = _identity()

    repository = PostgresUserIdentityRepository(
        engine=postgres_engine,
    )

    resolver = AuthenticatedUserResolver(
        repository=repository,
    )

    def resolve() -> AuthenticatedUser:
        return resolver.resolve(identity)

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            users_resolved = list(
                executor.map(
                    lambda _: resolve(),
                    range(8),
                )
            )

        user_ids = {user.user_id.value for user in users_resolved}

        assert len(user_ids) == 1

        with postgres_engine.connect() as connection:
            mapping_count = connection.execute(
                select(func.count())
                .select_from(auth_identities)
                .where(
                    auth_identities.c.issuer == identity.issuer,
                    auth_identities.c.subject == identity.subject,
                )
            ).scalar_one()

        assert mapping_count == 1

    finally:
        _delete_identity_user(
            postgres_engine,
            identity,
        )
