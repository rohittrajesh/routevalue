"""Resolve verified external identities into RouteValue users."""

from dataclasses import dataclass

from routevalue.application.identity import (
    AuthenticatedUser,
    VerifiedExternalIdentity,
)
from routevalue.application.ports import UserIdentityRepository


@dataclass(frozen=True, slots=True)
class AuthenticatedUserResolver:
    """Resolve verified authentication identities to internal users."""

    repository: UserIdentityRepository

    def resolve(
        self,
        identity: VerifiedExternalIdentity,
    ) -> AuthenticatedUser:
        """Return the permanent RouteValue user for a verified identity."""

        user_id = self.repository.get_or_create_user_id(identity)

        return AuthenticatedUser(
            user_id=user_id,
        )
