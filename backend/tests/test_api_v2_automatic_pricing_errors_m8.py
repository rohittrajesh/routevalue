"""M8-R3 tests for safe automatic gasoline pricing HTTP failures."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_trip_evaluations import (
    get_profile_driven_trip_evaluation_service,
)
from routevalue.application.gasoline_price_failures import (
    GasolinePriceProviderError,
    GasolinePriceProviderFailureReason,
    GasolinePriceUnavailableError,
    GasolinePriceUnavailableReason,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.domain.identity import UserId
from routevalue.main import create_app

_PATH = "/api/v2/trip-evaluations"


def make_body() -> dict[str, object]:
    return {
        "origin": {
            "display_name": "UC San Diego",
            "latitude": 32.8801,
            "longitude": -117.234,
        },
        "destination": {
            "display_name": "Downtown San Diego",
            "latitude": 32.7157,
            "longitude": -117.1611,
        },
    }


def make_client(error: Exception) -> tuple[TestClient, Mock]:
    user_id = UserId(value=uuid4())
    service = Mock()
    service.evaluate_trip.side_effect = error

    app = create_app()
    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)
    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = lambda: service

    return TestClient(app), service


@pytest.mark.parametrize(
    ("reason", "status_code", "expected_code"),
    [
        (
            GasolinePriceUnavailableReason.PRICE_NOT_FOUND,
            409,
            "gasoline_price_unavailable",
        ),
        (
            GasolinePriceUnavailableReason.UNSUPPORTED_GRADE,
            409,
            "gasoline_price_unavailable",
        ),
        (
            GasolinePriceUnavailableReason.UNSUPPORTED_GEOGRAPHY,
            409,
            "gasoline_price_unavailable",
        ),
        (
            GasolinePriceUnavailableReason.GRADE_MISMATCH,
            409,
            "gasoline_price_unavailable",
        ),
        (
            GasolinePriceUnavailableReason.GEOGRAPHY_MISMATCH,
            409,
            "gasoline_price_unavailable",
        ),
        (
            GasolinePriceUnavailableReason.PRICE_STALE,
            503,
            "gasoline_price_stale",
        ),
        (
            GasolinePriceUnavailableReason.PROVIDER_UNAVAILABLE,
            503,
            "gasoline_price_provider_unavailable",
        ),
        (
            GasolinePriceUnavailableReason.INVALID_QUOTE,
            502,
            "gasoline_price_invalid",
        ),
    ],
)
def test_unavailable_price_returns_sanitized_error(
    reason: GasolinePriceUnavailableReason,
    status_code: int,
    expected_code: str,
) -> None:
    client, service = make_client(
        GasolinePriceUnavailableError(reason),
    )

    with client:
        response = client.post(_PATH, json=make_body())

    assert response.status_code == status_code
    assert response.json()["code"] == expected_code
    assert isinstance(response.json()["detail"], str)
    assert response.json()["detail"]
    assert "Traceback" not in response.text
    assert "DATABASE_URL" not in response.text
    service.evaluate_trip.assert_called_once()


@pytest.mark.parametrize(
    ("reason", "status_code", "expected_code"),
    [
        (
            GasolinePriceProviderFailureReason.TIMEOUT,
            503,
            "gasoline_price_provider_unavailable",
        ),
        (
            GasolinePriceProviderFailureReason.TRANSPORT_ERROR,
            503,
            "gasoline_price_provider_unavailable",
        ),
        (
            GasolinePriceProviderFailureReason.RATE_LIMITED,
            503,
            "gasoline_price_provider_unavailable",
        ),
        (
            GasolinePriceProviderFailureReason.CONFIGURATION_ERROR,
            503,
            "gasoline_price_provider_unavailable",
        ),
        (
            GasolinePriceProviderFailureReason.INVALID_RESPONSE,
            502,
            "gasoline_price_invalid",
        ),
    ],
)
def test_provider_failure_returns_sanitized_error(
    reason: GasolinePriceProviderFailureReason,
    status_code: int,
    expected_code: str,
) -> None:
    client, service = make_client(
        GasolinePriceProviderError(reason),
    )

    with client:
        response = client.post(_PATH, json=make_body())

    assert response.status_code == status_code
    assert response.json()["code"] == expected_code
    assert "Traceback" not in response.text
    service.evaluate_trip.assert_called_once()


def test_automatic_error_mapping_does_not_require_manual_price() -> None:
    client, service = make_client(
        GasolinePriceUnavailableError(GasolinePriceUnavailableReason.PRICE_STALE)
    )

    with client:
        response = client.post(_PATH, json=make_body())

    assert response.status_code == 503

    assert service.evaluate_trip.call_args.kwargs["fuel_price_per_gallon"] is None
    assert service.evaluate_trip.call_args.kwargs["price_per_kilowatt_hour"] is None
