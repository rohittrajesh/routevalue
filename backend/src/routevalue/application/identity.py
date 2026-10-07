"""Provider-neutral authentication and identity models."""

from dataclasses import dataclass

from routevalue.domain.identity import UserId


class InvalidAuthenticationError(Exception):
    """An authentication credential is invalid or unacceptable."""


class AuthenticationVerificationUnavailableError(RuntimeError):
    """Authentication cannot currently be verified by the trusted provider."""


@dataclass(frozen=True, slots=True)
class VerifiedExternalIdentity:
    """External identity returned by trusted credential verification."""

    issuer: str
    subject: str

    def __post_init__(self) -> None:
        if not isinstance(self.issuer, str) or not self.issuer.strip():
            raise ValueError("authentication issuer cannot be blank")

        if not isinstance(self.subject, str) or not self.subject.strip():
            raise ValueError("authentication subject cannot be blank")


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """An authenticated caller resolved to an internal RouteValue user."""

    user_id: UserId

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise TypeError("AuthenticatedUser requires a UserId")
