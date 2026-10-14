"""Provider-neutral gasoline pricing failure contracts."""

from enum import StrEnum


class GasolinePriceProviderFailureReason(StrEnum):
    """Operational reasons a gasoline price lookup cannot complete."""

    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    INVALID_RESPONSE = "invalid_response"
    CONFIGURATION_ERROR = "configuration_error"


class GasolinePriceProviderError(RuntimeError):
    """A typed operational failure from a gasoline pricing provider.

    Provider-specific HTTP responses, credentials, and internal
    exception details must not leak into the public error message.
    """

    def __init__(
        self,
        reason: GasolinePriceProviderFailureReason,
    ) -> None:
        if not isinstance(reason, GasolinePriceProviderFailureReason):
            raise TypeError("reason must be a GasolinePriceProviderFailureReason")

        self.reason = reason
        super().__init__(reason.value)


class GasolinePriceUnavailableReason(StrEnum):
    """Reasons automatic gasoline pricing cannot produce a usable quote."""

    PRICE_NOT_FOUND = "price_not_found"
    UNSUPPORTED_GRADE = "unsupported_grade"
    UNSUPPORTED_GEOGRAPHY = "unsupported_geography"
    PRICE_STALE = "price_stale"
    GRADE_MISMATCH = "grade_mismatch"
    GEOGRAPHY_MISMATCH = "geography_mismatch"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_QUOTE = "invalid_quote"


class GasolinePriceUnavailableError(RuntimeError):
    """Application-level inability to obtain usable gasoline pricing."""

    def __init__(
        self,
        reason: GasolinePriceUnavailableReason,
    ) -> None:
        if not isinstance(reason, GasolinePriceUnavailableReason):
            raise TypeError("reason must be a GasolinePriceUnavailableReason")

        self.reason = reason
        super().__init__(reason.value)
