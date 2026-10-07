"""PostgreSQL persistence for RouteValue user identity mappings."""

from uuid import UUID, uuid4

from sqlalchemy import Connection, delete, insert, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import Engine

from routevalue.application.identity import VerifiedExternalIdentity
from routevalue.domain.identity import UserId
from routevalue.infrastructure.persistence.schema import (
    auth_identities,
    users,
)


class UserIdentityPersistenceError(RuntimeError):
    """Persisted user identity state violated a RouteValue invariant."""


class PostgresUserIdentityRepository:
    """Atomically map verified external identities to internal users."""

    def __init__(
        self,
        *,
        engine: Engine,
    ) -> None:
        self._engine = engine

    def get_or_create_user_id(
        self,
        identity: VerifiedExternalIdentity,
    ) -> UserId:
        """Return one stable internal user for the verified identity."""

        with self._engine.begin() as connection:
            existing = _find_user_id(
                connection,
                identity,
            )

            if existing is not None:
                return existing

            candidate = UserId(value=uuid4())

            connection.execute(
                insert(users).values(
                    id=candidate.value,
                )
            )

            inserted_user_id = connection.execute(
                postgresql_insert(auth_identities)
                .values(
                    id=uuid4(),
                    user_id=candidate.value,
                    issuer=identity.issuer,
                    subject=identity.subject,
                )
                .on_conflict_do_nothing(
                    constraint=("uq_auth_identities_issuer_subject"),
                )
                .returning(auth_identities.c.user_id)
            ).scalar_one_or_none()

            if inserted_user_id is not None:
                if inserted_user_id != candidate.value:
                    raise UserIdentityPersistenceError(
                        "created identity returned an unexpected user id"
                    )

                return candidate

            connection.execute(delete(users).where(users.c.id == candidate.value))

            winner = _find_user_id(
                connection,
                identity,
            )

            if winner is None:
                raise UserIdentityPersistenceError(
                    "conflicting identity mapping could not be resolved"
                )

            return winner


def _find_user_id(
    connection: Connection,
    identity: VerifiedExternalIdentity,
) -> UserId | None:
    """Read the internal user mapped to one external identity."""

    stored_value = connection.execute(
        select(auth_identities.c.user_id).where(
            auth_identities.c.issuer == identity.issuer,
            auth_identities.c.subject == identity.subject,
        )
    ).scalar_one_or_none()

    if stored_value is None:
        return None

    if not isinstance(stored_value, UUID):
        raise UserIdentityPersistenceError("stored user identity is not a UUID")

    return UserId(
        value=stored_value,
    )
