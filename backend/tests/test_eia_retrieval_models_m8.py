"""M8 EIA retrieval contract and network-limit tests."""

from dataclasses import FrozenInstanceError

import pytest

from routevalue.infrastructure.pricing.eia_retrieval_models import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_MAX_DOWNLOAD_BYTES,
    DEFAULT_READ_TIMEOUT_SECONDS,
    EiaDownloadedWorkbook,
    EiaRetrievalError,
    EiaRetrievalFailureReason,
    EiaRetrievalLimits,
)


def test_default_limits() -> None:
    limits = EiaRetrievalLimits()

    assert limits.connect_timeout_seconds == 10.0
    assert limits.read_timeout_seconds == 20.0
    assert limits.max_download_bytes == 10 * 1024 * 1024

    assert limits.connect_timeout_seconds == DEFAULT_CONNECT_TIMEOUT_SECONDS
    assert limits.read_timeout_seconds == DEFAULT_READ_TIMEOUT_SECONDS
    assert limits.max_download_bytes == DEFAULT_MAX_DOWNLOAD_BYTES


def test_custom_limits_are_preserved() -> None:
    limits = EiaRetrievalLimits(
        connect_timeout_seconds=5.0,
        read_timeout_seconds=15.0,
        max_download_bytes=1024,
    )

    assert limits.connect_timeout_seconds == 5.0
    assert limits.read_timeout_seconds == 15.0
    assert limits.max_download_bytes == 1024


@pytest.mark.parametrize(
    "value",
    [
        0.0,
        -1.0,
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_invalid_connect_timeout_is_rejected(
    value: float,
) -> None:
    with pytest.raises(ValueError):
        EiaRetrievalLimits(connect_timeout_seconds=value)


@pytest.mark.parametrize(
    "value",
    [
        0.0,
        -1.0,
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_invalid_read_timeout_is_rejected(
    value: float,
) -> None:
    with pytest.raises(ValueError):
        EiaRetrievalLimits(read_timeout_seconds=value)


@pytest.mark.parametrize(
    "value",
    [0, -1, -100],
)
def test_invalid_download_size_is_rejected(value: int) -> None:
    with pytest.raises(ValueError):
        EiaRetrievalLimits(max_download_bytes=value)


def test_boolean_download_size_is_rejected() -> None:
    with pytest.raises(TypeError):
        EiaRetrievalLimits(max_download_bytes=True)


def test_non_numeric_timeout_is_rejected() -> None:
    with pytest.raises(TypeError):
        EiaRetrievalLimits(
            read_timeout_seconds="slow"  # type: ignore[arg-type]
        )


def test_limits_are_immutable() -> None:
    limits = EiaRetrievalLimits()

    with pytest.raises(FrozenInstanceError):
        limits.max_download_bytes = 100  # type: ignore[misc]


def test_downloaded_workbook_preserves_bytes() -> None:
    workbook = EiaDownloadedWorkbook(
        source_url="https://www.eia.gov/example.xls",
        content=b"example-workbook-bytes",
    )

    assert workbook.content == b"example-workbook-bytes"
    assert workbook.source_url.startswith("https://")


def test_empty_download_is_rejected() -> None:
    with pytest.raises(ValueError, match="content cannot be empty"):
        EiaDownloadedWorkbook(
            source_url="https://www.eia.gov/example.xls",
            content=b"",
        )


def test_blank_source_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="source_url cannot be blank"):
        EiaDownloadedWorkbook(
            source_url=" ",
            content=b"workbook",
        )


@pytest.mark.parametrize(
    "reason",
    list(EiaRetrievalFailureReason),
)
def test_retrieval_error_preserves_reason(
    reason: EiaRetrievalFailureReason,
) -> None:
    error = EiaRetrievalError(reason)

    assert error.reason is reason
    assert error.status_code is None
    assert str(error) == reason.value


def test_http_failure_preserves_status() -> None:
    error = EiaRetrievalError(
        EiaRetrievalFailureReason.HTTP_ERROR,
        status_code=503,
    )

    assert error.status_code == 503
    assert error.reason is EiaRetrievalFailureReason.HTTP_ERROR


def test_invalid_error_reason_is_rejected() -> None:
    with pytest.raises(TypeError):
        EiaRetrievalError(
            "timeout"  # type: ignore[arg-type]
        )


def test_invalid_status_code_is_rejected() -> None:
    with pytest.raises(ValueError):
        EiaRetrievalError(
            EiaRetrievalFailureReason.HTTP_ERROR,
            status_code=999,
        )
