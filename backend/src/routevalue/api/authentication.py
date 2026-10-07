"""FastAPI authentication boundary for RouteValue V2 resources."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from routevalue.api.errors import (
    AuthenticationRequiredError,
    AuthenticationServiceUnavailableError,
    ServiceConfigurationError,
)
from routevalue.application.identity import (
    AuthenticationVerificationUnavailableError,
    InvalidAuthenticationError,
    VerifiedExternalIdentity,
)
from routevalue.application.ports import AuthenticationVerifier
from routevalue.infrastructure.auth.neon_config import (
    NeonAuthConfigurationError,
    load_neon_jwt_settings,
)
from routevalue.infrastructure.auth.neon_jwt import (
    NeonJWTAuthenticationVerifier,
)

_bearer_scheme = HTTPBearer(
    auto_error=False,
)


@lru_cache(maxsize=1)
def get_authentication_verifier() -> AuthenticationVerifier:
    """Build and reuse the production Neon authentication verifier."""

    try:
        settings = load_neon_jwt_settings()
    except NeonAuthConfigurationError as exc:
        raise ServiceConfigurationError("authentication configuration is unavailable") from exc

    return NeonJWTAuthenticationVerifier(
        settings=settings,
    )


def get_bearer_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ],
) -> str:
    """Require and extract one HTTP bearer credential."""

    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AuthenticationRequiredError

    return credentials.credentials


def get_verified_external_identity(
    token: Annotated[
        str,
        Depends(get_bearer_token),
    ],
    verifier: Annotated[
        AuthenticationVerifier,
        Depends(get_authentication_verifier),
    ],
) -> VerifiedExternalIdentity:
    """Authenticate one bearer credential at the FastAPI boundary."""

    try:
        return verifier.verify_token(token)

    except InvalidAuthenticationError:
        raise AuthenticationRequiredError from None

    except AuthenticationVerificationUnavailableError:
        raise AuthenticationServiceUnavailableError from None
