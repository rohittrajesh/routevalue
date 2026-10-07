"""Configuration for Neon Managed Better Auth JWT verification."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit


class NeonAuthConfigurationError(RuntimeError):
    """Trusted Neon Auth configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class NeonJWTSettings:
    """Validated, branch-specific JWT verification settings."""

    issuer: str
    jwks_url: str
    audience: str | None = None


def _https_url(
    value: str | None,
    *,
    name: str,
) -> SplitResult:
    """Parse a configured HTTPS URL without exposing its contents on failure."""

    if value is None or not value.strip():
        raise NeonAuthConfigurationError(f"{name} must be configured")

    try:
        parsed = urlsplit(value.strip())
        _ = parsed.port
    except ValueError:
        raise NeonAuthConfigurationError(f"{name} must be a valid HTTPS URL") from None

    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise NeonAuthConfigurationError(f"{name} must be a valid HTTPS URL")

    return parsed


def load_neon_jwt_settings(
    *,
    environment: Mapping[str, str] | None = None,
) -> NeonJWTSettings:
    """Load trusted JWT issuer and JWKS URL; no network calls are made."""

    values = os.environ if environment is None else environment

    base = _https_url(
        values.get("NEON_AUTH_BASE_URL"),
        name="NEON_AUTH_BASE_URL",
    )

    jwks = _https_url(
        values.get("NEON_AUTH_JWKS_URL"),
        name="NEON_AUTH_JWKS_URL",
    )

    audience_raw = values.get("ROUTEVALUE_AUTH_AUDIENCE")

    if audience_raw is not None and not audience_raw.strip():
        raise NeonAuthConfigurationError("ROUTEVALUE_AUTH_AUDIENCE cannot be blank")

    return NeonJWTSettings(
        issuer=f"{base.scheme}://{base.netloc}",
        jwks_url=jwks.geturl(),
        audience=audience_raw.strip() if audience_raw is not None else None,
    )
