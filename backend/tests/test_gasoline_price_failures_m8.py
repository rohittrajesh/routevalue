"""M8 typed gasoline pricing failure tests."""

import pytest

from routevalue.application.gasoline_price_failures import (
    GasolinePriceProviderError,
    GasolinePriceProviderFailureReason,
    GasolinePriceUnavailableError,
    GasolinePriceUnavailableReason,
)


@pytest.mark.parametrize(
    "reason",
    list(GasolinePriceProviderFailureReason),
)
def test_provider_error_preserves_structured_reason(
    reason: GasolinePriceProviderFailureReason,
) -> None:
    error = GasolinePriceProviderError(reason)

    assert error.reason is reason
    assert str(error) == reason.value
    assert isinstance(error, RuntimeError)


@pytest.mark.parametrize(
    "reason",
    list(GasolinePriceUnavailableReason),
)
def test_unavailable_error_preserves_structured_reason(
    reason: GasolinePriceUnavailableReason,
) -> None:
    error = GasolinePriceUnavailableError(reason)

    assert error.reason is reason
    assert str(error) == reason.value
    assert isinstance(error, RuntimeError)


def test_provider_error_rejects_invalid_reason() -> None:
    with pytest.raises(
        TypeError,
        match="GasolinePriceProviderFailureReason",
    ):
        GasolinePriceProviderError(
            "timeout"  # type: ignore[arg-type]
        )


def test_unavailable_error_rejects_invalid_reason() -> None:
    with pytest.raises(
        TypeError,
        match="GasolinePriceUnavailableReason",
    ):
        GasolinePriceUnavailableError(
            "price_stale"  # type: ignore[arg-type]
        )


def test_provider_error_can_be_caught_by_reason() -> None:
    try:
        raise GasolinePriceProviderError(GasolinePriceProviderFailureReason.RATE_LIMITED)
    except GasolinePriceProviderError as error:
        assert error.reason is GasolinePriceProviderFailureReason.RATE_LIMITED


def test_unavailable_error_can_be_caught_by_reason() -> None:
    try:
        raise GasolinePriceUnavailableError(GasolinePriceUnavailableReason.UNSUPPORTED_GRADE)
    except GasolinePriceUnavailableError as error:
        assert error.reason is GasolinePriceUnavailableReason.UNSUPPORTED_GRADE


def test_provider_error_supports_exception_chaining() -> None:
    original_error = TimeoutError("internal transport details")

    try:
        try:
            raise original_error
        except TimeoutError as exc:
            raise GasolinePriceProviderError(GasolinePriceProviderFailureReason.TIMEOUT) from exc
    except GasolinePriceProviderError as error:
        assert error.reason is GasolinePriceProviderFailureReason.TIMEOUT
        assert error.__cause__ is original_error

        # Public-facing text must not contain internal details.
        assert "internal transport details" not in str(error)


def test_provider_and_unavailable_errors_are_distinct() -> None:
    provider_error = GasolinePriceProviderError(GasolinePriceProviderFailureReason.INVALID_RESPONSE)

    unavailable_error = GasolinePriceUnavailableError(GasolinePriceUnavailableReason.INVALID_QUOTE)

    assert not isinstance(
        provider_error,
        GasolinePriceUnavailableError,
    )

    assert not isinstance(
        unavailable_error,
        GasolinePriceProviderError,
    )
