"""Offline EdDSA/JWKS verification tests for Neon Managed Better Auth."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError
from jwt.utils import base64url_encode

from routevalue.application.identity import (
    AuthenticationVerificationUnavailableError,
    InvalidAuthenticationError,
    VerifiedExternalIdentity,
)
from routevalue.infrastructure.auth.neon_config import (
    NeonAuthConfigurationError,
    NeonJWTSettings,
    load_neon_jwt_settings,
)
from routevalue.infrastructure.auth.neon_jwt import (
    NeonJWTAuthenticationVerifier,
)

_ISSUER = "https://branch.neonauth.us-east-2.aws.neon.tech"
_JWKS_URL = f"{_ISSUER}/neondb/auth/jwks"
_KEY_ID = "test-ed25519-key"


def _settings(
    *,
    audience: str | None = None,
) -> NeonJWTSettings:
    return NeonJWTSettings(
        issuer=_ISSUER,
        jwks_url=_JWKS_URL,
        audience=audience,
    )


class StaticJwksClient(PyJWKClient):
    """Serve a local Ed25519 public key without network access."""

    def __init__(
        self,
        key: Ed25519PrivateKey,
    ) -> None:
        super().__init__(_JWKS_URL)

        raw = key.public_key().public_bytes(
            Encoding.Raw,
            PublicFormat.Raw,
        )

        self._static_jwks: dict[str, object] = {
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "alg": "EdDSA",
                    "kid": _KEY_ID,
                    "use": "sig",
                    "x": base64url_encode(raw).decode("ascii"),
                }
            ],
        }

    def fetch_data(self) -> Any:
        return self._static_jwks


@pytest.fixture
def private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture
def verifier(
    private_key: Ed25519PrivateKey,
) -> NeonJWTAuthenticationVerifier:
    return NeonJWTAuthenticationVerifier(
        settings=_settings(),
        jwks_client=StaticJwksClient(private_key),
    )


def _token(
    key: Ed25519PrivateKey,
    **changes: object,
) -> str:
    now = datetime.now(UTC)

    claims: dict[str, object] = {
        "iss": _ISSUER,
        "sub": "neon-user-123",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
    }

    claims.update(changes)

    return jwt.encode(
        claims,
        key,
        algorithm="EdDSA",
        headers={"kid": _KEY_ID},
    )


def test_config_extracts_origin_from_auth_base_url() -> None:
    settings = load_neon_jwt_settings(
        environment={
            "NEON_AUTH_BASE_URL": f"{_ISSUER}/neondb/auth",
            "NEON_AUTH_JWKS_URL": _JWKS_URL,
        }
    )

    assert settings == _settings()


def test_config_optional_audience() -> None:
    settings = load_neon_jwt_settings(
        environment={
            "NEON_AUTH_BASE_URL": f"{_ISSUER}/neondb/auth",
            "NEON_AUTH_JWKS_URL": _JWKS_URL,
            "ROUTEVALUE_AUTH_AUDIENCE": "routevalue-api",
        }
    )

    assert settings.audience == "routevalue-api"


@pytest.mark.parametrize(
    "missing",
    [
        "NEON_AUTH_BASE_URL",
        "NEON_AUTH_JWKS_URL",
    ],
)
def test_config_requires_both_urls(
    missing: str,
) -> None:
    environment = {
        "NEON_AUTH_BASE_URL": f"{_ISSUER}/neondb/auth",
        "NEON_AUTH_JWKS_URL": _JWKS_URL,
    }

    del environment[missing]

    with pytest.raises(
        NeonAuthConfigurationError,
        match=missing,
    ):
        load_neon_jwt_settings(environment=environment)


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://example.test/auth",
        "not-a-url",
        "https://user:secret@example.test/auth",
        "https://example.test/auth#fragment",
        "https://example.test:bad/auth",
    ],
)
def test_config_rejects_unsafe_urls_without_leaking_secrets(
    bad_url: str,
) -> None:
    with pytest.raises(NeonAuthConfigurationError) as exc_info:
        load_neon_jwt_settings(
            environment={
                "NEON_AUTH_BASE_URL": f"{_ISSUER}/neondb/auth",
                "NEON_AUTH_JWKS_URL": bad_url,
            }
        )

    assert "secret" not in str(exc_info.value)


def test_config_rejects_blank_audience() -> None:
    with pytest.raises(
        NeonAuthConfigurationError,
        match="ROUTEVALUE_AUTH_AUDIENCE",
    ):
        load_neon_jwt_settings(
            environment={
                "NEON_AUTH_BASE_URL": f"{_ISSUER}/neondb/auth",
                "NEON_AUTH_JWKS_URL": _JWKS_URL,
                "ROUTEVALUE_AUTH_AUDIENCE": "  ",
            }
        )


def test_valid_signed_token(
    verifier: NeonJWTAuthenticationVerifier,
    private_key: Ed25519PrivateKey,
) -> None:
    identity = verifier.verify_token(_token(private_key))

    assert identity == VerifiedExternalIdentity(
        issuer=_ISSUER,
        subject="neon-user-123",
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "https://attacker.example.test"},
        {"exp": 1},
        {"sub": ""},
        {"sub": None},
        {"nbf": 9999999999},
    ],
)
def test_invalid_claims_rejected(
    verifier: NeonJWTAuthenticationVerifier,
    private_key: Ed25519PrivateKey,
    changes: dict[str, object],
) -> None:
    with pytest.raises(InvalidAuthenticationError):
        verifier.verify_token(_token(private_key, **changes))


def test_missing_exp_is_rejected(
    verifier: NeonJWTAuthenticationVerifier,
    private_key: Ed25519PrivateKey,
) -> None:
    now = int(datetime.now(UTC).timestamp())

    token = jwt.encode(
        {
            "iss": _ISSUER,
            "sub": "neon-user-123",
            "iat": now,
        },
        private_key,
        algorithm="EdDSA",
        headers={"kid": _KEY_ID},
    )

    with pytest.raises(InvalidAuthenticationError):
        verifier.verify_token(token)


def test_missing_issuer_is_rejected(
    verifier: NeonJWTAuthenticationVerifier,
    private_key: Ed25519PrivateKey,
) -> None:
    now = datetime.now(UTC)

    token = jwt.encode(
        {
            "sub": "neon-user-123",
            "exp": int((now + timedelta(minutes=15)).timestamp()),
        },
        private_key,
        algorithm="EdDSA",
        headers={"kid": _KEY_ID},
    )

    with pytest.raises(InvalidAuthenticationError):
        verifier.verify_token(token)


def test_wrong_signing_key_is_rejected(
    verifier: NeonJWTAuthenticationVerifier,
) -> None:
    incorrect_key = Ed25519PrivateKey.generate()

    with pytest.raises(InvalidAuthenticationError):
        verifier.verify_token(_token(incorrect_key))


def test_unknown_signing_key_is_rejected(
    verifier: NeonJWTAuthenticationVerifier,
    private_key: Ed25519PrivateKey,
) -> None:
    now = datetime.now(UTC)

    token = jwt.encode(
        {
            "iss": _ISSUER,
            "sub": "neon-user-123",
            "exp": int((now + timedelta(minutes=15)).timestamp()),
        },
        private_key,
        algorithm="EdDSA",
        headers={"kid": "unrecognized-signing-key"},
    )

    with pytest.raises(InvalidAuthenticationError):
        verifier.verify_token(token)


def test_rejects_wrong_signature_algorithm(
    verifier: NeonJWTAuthenticationVerifier,
) -> None:
    token = jwt.encode(
        {
            "iss": _ISSUER,
            "sub": "user",
            "exp": 9999999999,
        },
        "not-the-real-secret-very-long-32-plus-bytes",
        algorithm="HS256",
        headers={"kid": _KEY_ID},
    )

    with pytest.raises(InvalidAuthenticationError):
        verifier.verify_token(token)


@pytest.mark.parametrize(
    "bad_token",
    [
        "",
        "   ",
        "fake.token",
        "junk",
        "  a.b.c",
        "a.b.c ",
        "x" * 16385,
    ],
)
def test_malformed_bearer_rejected(
    verifier: NeonJWTAuthenticationVerifier,
    bad_token: str,
) -> None:
    with pytest.raises(InvalidAuthenticationError):
        verifier.verify_token(bad_token)


def test_audience_is_checked_only_when_configured(
    private_key: Ed25519PrivateKey,
) -> None:
    verifier = NeonJWTAuthenticationVerifier(
        settings=_settings(audience="routevalue-api"),
        jwks_client=StaticJwksClient(private_key),
    )

    valid_identity = verifier.verify_token(_token(private_key, aud="routevalue-api"))

    assert valid_identity.subject == "neon-user-123"

    with pytest.raises(InvalidAuthenticationError):
        verifier.verify_token(_token(private_key, aud="wrong-api"))

    with pytest.raises(InvalidAuthenticationError):
        verifier.verify_token(_token(private_key))


def test_jwks_connection_failure_is_distinct(
    private_key: Ed25519PrivateKey,
) -> None:
    class UnreachableJWKS(PyJWKClient):
        def fetch_data(self) -> Any:
            raise PyJWKClientConnectionError("network unavailable")

    verifier = NeonJWTAuthenticationVerifier(
        settings=_settings(),
        jwks_client=UnreachableJWKS(_JWKS_URL),
    )

    with pytest.raises(AuthenticationVerificationUnavailableError):
        verifier.verify_token(_token(private_key))
