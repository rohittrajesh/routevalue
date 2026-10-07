"""Resolve authenticated HTTP callers into internal RouteValue users."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.engine import Engine

from routevalue.api.authentication import (
    get_verified_external_identity,
)
from routevalue.api.errors import (
    ServiceConfigurationError,
)
from routevalue.application.identity import (
    AuthenticatedUser,
    VerifiedExternalIdentity,
)
from routevalue.application.ports import (
    UserIdentityRepository,
)
from routevalue.application.user_identity import (
    AuthenticatedUserResolver,
)
from routevalue.infrastructure.persistence.config import (
    DatabaseConfigurationError,
)
from routevalue.infrastructure.persistence.connection import (
    create_application_engine,
)
from routevalue.infrastructure.persistence.user_identity import (
    PostgresUserIdentityRepository,
)


@lru_cache(maxsize=1)
def get_application_database_engine() -> Engine:
    """Build and reuse the production application database engine."""

    try:
        return create_application_engine()

    except DatabaseConfigurationError as exc:
        raise ServiceConfigurationError("user identity persistence is unavailable") from exc


@lru_cache(maxsize=1)
def get_user_identity_repository() -> UserIdentityRepository:
    """Build and reuse the production identity repository."""

    return PostgresUserIdentityRepository(
        engine=get_application_database_engine(),
    )


def get_authenticated_user_resolver(
    repository: Annotated[
        UserIdentityRepository,
        Depends(get_user_identity_repository),
    ],
) -> AuthenticatedUserResolver:
    """Compose the application user-resolution service."""

    return AuthenticatedUserResolver(
        repository=repository,
    )


def get_authenticated_user(
    identity: Annotated[
        VerifiedExternalIdentity,
        Depends(get_verified_external_identity),
    ],
    resolver: Annotated[
        AuthenticatedUserResolver,
        Depends(get_authenticated_user_resolver),
    ],
) -> AuthenticatedUser:
    """Resolve a verified external identity into a RouteValue user."""

    return resolver.resolve(identity)


def close_user_identity_resources() -> None:
    """Dispose cached persistence resources during application shutdown."""

    get_user_identity_repository.cache_clear()

    if get_application_database_engine.cache_info().currsize:
        engine = get_application_database_engine()

        engine.dispose()

    get_application_database_engine.cache_clear()
