"""Tests for provider-neutral authentication and user identity."""

from dataclasses import FrozenInstanceError
from typing import cast
from uuid import UUID, uuid4

import pytest

from routevalue.application.identity import (
    AuthenticatedUser,
    InvalidAuthenticationError,
    VerifiedExternalIdentity,
)
from routevalue.application.ports import AuthenticationVerifier
from routevalue.domain.identity import UserId


def _set_attribute(
    target: object,
    name: str,
    value: object,
) -> None:
    """Attempt a runtime attribute assignment for immutability tests."""

    setattr(target, name, value)


def test_user_id_wraps_internal_uuid() -> None:
    identifier = uuid4()

    user_id = UserId(value=identifier)

    assert user_id.value == identifier


def test_user_ids_have_value_equality() -> None:
    identifier = uuid4()

    first = UserId(value=identifier)
    second = UserId(value=identifier)

    assert first == second
    assert hash(first) == hash(second)
    assert first != UserId(value=uuid4())


def test_user_id_is_immutable() -> None:
    user_id = UserId(value=uuid4())

    with pytest.raises(FrozenInstanceError):
        _set_attribute(
            user_id,
            "value",
            uuid4(),
        )


def test_user_id_rejects_external_string() -> None:
    with pytest.raises(TypeError):
        UserId(value=cast(UUID, "external-user-123"))


def test_verified_external_identity_preserves_claims() -> None:
    identity = VerifiedExternalIdentity(
        issuer="https://auth.example.test",
        subject="external-user-123",
    )

    assert identity.issuer == "https://auth.example.test"
    assert identity.subject == "external-user-123"


@pytest.mark.parametrize(
    ("issuer", "subject"),
    [
        ("", "subject"),
        ("   ", "subject"),
        ("https://auth.example.test", ""),
        ("https://auth.example.test", "   "),
    ],
)
def test_verified_external_identity_rejects_blanks(
    issuer: str,
    subject: str,
) -> None:
    with pytest.raises(ValueError):
        VerifiedExternalIdentity(
            issuer=issuer,
            subject=subject,
        )


def test_verified_external_identity_is_immutable() -> None:
    identity = VerifiedExternalIdentity(
        issuer="https://auth.example.test",
        subject="external-user-123",
    )

    with pytest.raises(FrozenInstanceError):
        _set_attribute(
            identity,
            "subject",
            "different-user",
        )


def test_authenticated_user_contains_internal_user_id() -> None:
    user_id = UserId(value=uuid4())

    user = AuthenticatedUser(user_id=user_id)

    assert user.user_id == user_id
    assert not hasattr(user, "subject")
    assert not hasattr(user, "issuer")


def test_authenticated_user_rejects_raw_uuid() -> None:
    with pytest.raises(TypeError):
        AuthenticatedUser(user_id=cast(UserId, uuid4()))


def test_application_accepts_provider_neutral_verifier() -> None:
    class FakeAuthenticationVerifier:
        def verify_token(
            self,
            token: str,
        ) -> VerifiedExternalIdentity:
            assert token == "valid-test-token"

            return VerifiedExternalIdentity(
                issuer="https://auth.example.test",
                subject="external-user-123",
            )

    def verify_using_port(
        verifier: AuthenticationVerifier,
    ) -> VerifiedExternalIdentity:
        return verifier.verify_token("valid-test-token")

    identity = verify_using_port(FakeAuthenticationVerifier())

    assert identity.issuer == "https://auth.example.test"
    assert identity.subject == "external-user-123"


def test_verifier_can_reject_invalid_credentials() -> None:
    class RejectingAuthenticationVerifier:
        def verify_token(
            self,
            token: str,
        ) -> VerifiedExternalIdentity:
            raise InvalidAuthenticationError

    verifier: AuthenticationVerifier = RejectingAuthenticationVerifier()

    with pytest.raises(InvalidAuthenticationError):
        verifier.verify_token("invalid-test-token")
