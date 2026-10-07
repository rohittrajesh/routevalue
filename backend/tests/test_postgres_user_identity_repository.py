"""Integration tests for PostgreSQL user identity resolution."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine

from routevalue.application.identity import (
    VerifiedExternalIdentity,
)
from routevalue.application.ports import (
    UserIdentityRepository,
)
from routevalue.domain.identity import UserId
from routevalue.infrastructure.persistence.schema import (
    auth_identities,
    users,
)
from routevalue.infrastructure.persistence.user_identity import (
    PostgresUserIdentityRepository,
)


def _identity(
    *,
    issuer: str | None = None,
    subject: str | None = None,
) -> VerifiedExternalIdentity:
    return VerifiedExternalIdentity(
        issuer=(issuer or f"https://auth-{uuid4().hex}.example.test"),
        subject=(subject or f"subject-{uuid4().hex}"),
    )


def _repository(
    engine: Engine,
) -> UserIdentityRepository:
    return PostgresUserIdentityRepository(
        engine=engine,
    )


def _delete_user(
    engine: Engine,
    user_id: UserId,
) -> None:
    with engine.begin() as connection:
        connection.execute(delete(users).where(users.c.id == user_id.value))


def test_repository_creates_persistent_user_mapping(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    identity = _identity()

    user_id = repository.get_or_create_user_id(identity)

    try:
        with postgres_engine.connect() as connection:
            stored_user = connection.execute(
                select(users.c.id).where(users.c.id == user_id.value)
            ).scalar_one()

            stored_mapping = connection.execute(
                select(auth_identities.c.user_id).where(
                    auth_identities.c.issuer == identity.issuer,
                    auth_identities.c.subject == identity.subject,
                )
            ).scalar_one()

        assert stored_user == user_id.value
        assert stored_mapping == user_id.value

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )


def test_repository_reuses_existing_identity_mapping(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    identity = _identity()

    first = repository.get_or_create_user_id(identity)

    try:
        second = repository.get_or_create_user_id(identity)

        assert second == first

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
        _delete_user(
            postgres_engine,
            first,
        )


def test_same_subject_from_different_issuers_gets_different_users(
    postgres_engine: Engine,
) -> None:
    repository = _repository(postgres_engine)

    subject = f"shared-{uuid4().hex}"

    first_identity = _identity(
        issuer=(f"https://auth-one-{uuid4().hex}.example.test"),
        subject=subject,
    )

    second_identity = _identity(
        issuer=(f"https://auth-two-{uuid4().hex}.example.test"),
        subject=subject,
    )

    first = repository.get_or_create_user_id(first_identity)

    second = repository.get_or_create_user_id(second_identity)

    try:
        assert first != second

    finally:
        _delete_user(
            postgres_engine,
            first,
        )

        _delete_user(
            postgres_engine,
            second,
        )


def test_concurrent_first_resolution_returns_single_user(
    postgres_engine: Engine,
) -> None:
    repository = PostgresUserIdentityRepository(
        engine=postgres_engine,
    )

    identity = _identity()

    def resolve() -> UserId:
        return repository.get_or_create_user_id(identity)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                lambda _: resolve(),
                range(8),
            )
        )

    unique_user_ids = {result.value for result in results}

    assert len(unique_user_ids) == 1

    user_id = results[0]

    try:
        with postgres_engine.connect() as connection:
            mapping_count = connection.execute(
                select(func.count())
                .select_from(auth_identities)
                .where(
                    auth_identities.c.issuer == identity.issuer,
                    auth_identities.c.subject == identity.subject,
                )
            ).scalar_one()

            user_count = connection.execute(
                select(func.count()).select_from(users).where(users.c.id == user_id.value)
            ).scalar_one()

        assert mapping_count == 1
        assert user_count == 1

    finally:
        _delete_user(
            postgres_engine,
            user_id,
        )
