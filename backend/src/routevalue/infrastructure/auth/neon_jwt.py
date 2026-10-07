"""Verify Neon Managed Better Auth JWTs with pinned EdDSA and JWKS."""

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError

from routevalue.application.identity import (
    AuthenticationVerificationUnavailableError,
    InvalidAuthenticationError,
    VerifiedExternalIdentity,
)
from routevalue.infrastructure.auth.neon_config import NeonJWTSettings


class NeonJWTAuthenticationVerifier:
    """Verify bearer JWTs without exposing Neon types to the application."""

    def __init__(
        self,
        *,
        settings: NeonJWTSettings,
        jwks_client: PyJWKClient | None = None,
    ) -> None:
        self._settings = settings

        self._jwks_client = jwks_client or PyJWKClient(
            settings.jwks_url,
            timeout=5,
            lifespan=300,
        )

    def verify_token(
        self,
        token: str,
    ) -> VerifiedExternalIdentity:
        """Return a verified subject, or reject invalid credentials."""

        if (
            not isinstance(token, str)
            or not token
            or token.strip() != token
            or len(token) > 16_384
            or token.count(".") != 2
        ):
            raise InvalidAuthenticationError("Invalid authentication token")

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)

            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["EdDSA"],
                issuer=self._settings.issuer,
                audience=self._settings.audience,
                options={
                    "require": ["iss", "sub", "exp"],
                    "verify_aud": self._settings.audience is not None,
                },
            )

        except PyJWKClientConnectionError:
            raise AuthenticationVerificationUnavailableError(
                "Authentication signing keys are temporarily unavailable"
            ) from None

        except (PyJWTError, ValueError, TypeError):
            raise InvalidAuthenticationError("Invalid authentication token") from None

        subject = claims.get("sub")

        if not isinstance(subject, str) or not subject.strip():
            raise InvalidAuthenticationError("Invalid authentication token")

        return VerifiedExternalIdentity(
            issuer=self._settings.issuer,
            subject=subject,
        )
