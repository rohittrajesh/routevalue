"""Contracts and safety limits for EIA XLS retrieval.

These models describe bounded workbook downloads and failures.
They contain no network operations or cache mutations.
"""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_READ_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024


class EiaRetrievalFailureReason(StrEnum):
    """Operational failures while retrieving an EIA workbook."""

    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    HTTP_ERROR = "http_error"
    DOWNLOAD_TOO_LARGE = "download_too_large"
    EMPTY_RESPONSE = "empty_response"
    INVALID_CONTENT = "invalid_content"
    UNSAFE_REDIRECT = "unsafe_redirect"


class EiaRetrievalError(Exception):
    """Structured retrieval failure with an optional HTTP status."""

    def __init__(
        self,
        reason: EiaRetrievalFailureReason,
        *,
        status_code: int | None = None,
    ) -> None:
        if not isinstance(reason, EiaRetrievalFailureReason):
            raise TypeError("reason must be an EiaRetrievalFailureReason")

        if status_code is not None:
            if isinstance(status_code, bool) or not isinstance(status_code, int):
                raise TypeError("status_code must be an integer")

            if not 100 <= status_code <= 599:
                raise ValueError("status_code must be a valid HTTP status")

        self.reason = reason
        self.status_code = status_code
        super().__init__(reason.value)


@dataclass(frozen=True, slots=True)
class EiaRetrievalLimits:
    """Immutable network and response-size safety limits."""

    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS
    max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES

    def __post_init__(self) -> None:
        for name in (
            "connect_timeout_seconds",
            "read_timeout_seconds",
        ):
            value = getattr(self, name)

            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric")

            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")

        if isinstance(self.max_download_bytes, bool) or not isinstance(
            self.max_download_bytes, int
        ):
            raise TypeError("max_download_bytes must be an integer")

        if self.max_download_bytes <= 0:
            raise ValueError("max_download_bytes must be positive")


@dataclass(frozen=True, slots=True)
class EiaDownloadedWorkbook:
    """A bounded raw XLS download awaiting parser validation.

    Successful construction does not imply that the workbook
    contains valid EIA observations.
    """

    source_url: str
    content: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.source_url, str):
            raise TypeError("source_url must be a string")

        if not self.source_url.strip():
            raise ValueError("source_url cannot be blank")

        if not isinstance(self.content, bytes):
            raise TypeError("content must be bytes")

        if not self.content:
            raise ValueError("content cannot be empty")
