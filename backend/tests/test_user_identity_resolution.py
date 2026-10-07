"""Tests for provider-neutral RouteValue user resolution."""

from uuid import uuid4

from routevalue.application.identity import (
    AuthenticatedUser,
    VerifiedExternalIdentity,
)
from routevalue.application.ports import UserIdentityRepository
from routevalue.application.user_identity import (
    AuthenticatedUserResolver,
)
from routevalue.domain.identity import UserId


class FakeUserIdentityRepository:
    """Deterministically map external identities to internal users."""

    def __init__(self) -> None:
        self._users: dict[
            VerifiedExternalIdentity,
            UserId,
        ] = {}

        self.requests: list[VerifiedExternalIdentity] = []

    def get_or_create_user_id(
        self,
        identity: VerifiedExternalIdentity,
    ) -> UserId:
        self.requests.append(identity)

        existing = self._users.get(identity)

        if existing is not None:
            return existing

        user_id = UserId(value=uuid4())

        self._users[identity] = user_id

        return user_id


def _identity(
    subject: str = "external-user-123",
) -> VerifiedExternalIdentity:
    return VerifiedExternalIdentity(
        issuer="https://auth.example.test",
        subject=subject,
    )


def _resolve_using_port(
    repository: UserIdentityRepository,
    identity: VerifiedExternalIdentity,
) -> AuthenticatedUser:
    resolver = AuthenticatedUserResolver(
        repository=repository,
    )

    return resolver.resolve(identity)


def test_resolver_returns_authenticated_internal_user() -> None:
    repository = FakeUserIdentityRepository()

    user = _resolve_using_port(
        repository,
        _identity(),
    )

    assert isinstance(user, AuthenticatedUser)
    assert isinstance(user.user_id, UserId)


def test_same_external_identity_resolves_to_same_user() -> None:
    repository = FakeUserIdentityRepository()
    resolver = AuthenticatedUserResolver(
        repository=repository,
    )

    identity = _identity()

    first = resolver.resolve(identity)
    second = resolver.resolve(identity)

    assert first == second
    assert first.user_id == second.user_id


def test_different_external_identities_resolve_to_different_users() -> None:
    repository = FakeUserIdentityRepository()
    resolver = AuthenticatedUserResolver(
        repository=repository,
    )

    first = resolver.resolve(_identity("external-user-1"))

    second = resolver.resolve(_identity("external-user-2"))

    assert first.user_id != second.user_id


def test_identity_issuer_is_part_of_mapping_key() -> None:
    repository = FakeUserIdentityRepository()
    resolver = AuthenticatedUserResolver(
        repository=repository,
    )

    first = resolver.resolve(
        VerifiedExternalIdentity(
            issuer="https://auth-one.example.test",
            subject="same-subject",
        )
    )

    second = resolver.resolve(
        VerifiedExternalIdentity(
            issuer="https://auth-two.example.test",
            subject="same-subject",
        )
    )

    assert first.user_id != second.user_id


def test_resolver_passes_verified_identity_without_mutation() -> None:
    repository = FakeUserIdentityRepository()
    resolver = AuthenticatedUserResolver(
        repository=repository,
    )

    identity = _identity()

    resolver.resolve(identity)

    assert repository.requests == [
        identity,
    ]
