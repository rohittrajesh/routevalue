"""M8-R4 tests for sanitized persisted-pricing failures."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from routevalue.api.errors import ServiceConfigurationError
from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_trip_evaluations import (
    get_profile_driven_trip_evaluation_service,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.domain.identity import UserId
from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    EiaPricingPersistenceError,
)
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


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (
            EiaPricingPersistenceError("internal snapshot detail"),
            502,
            "gasoline_price_invalid",
        ),
        (
            ServiceConfigurationError("internal database configuration"),
            503,
            "gasoline_price_provider_unavailable",
        ),
    ],
)
def test_pricing_persistence_failure_is_sanitized(
    error: Exception,
    status: int,
    code: str,
) -> None:
    service = Mock()
    service.evaluate_trip.side_effect = error

    app = create_app()
    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(
        user_id=UserId(value=uuid4())
    )
    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(_PATH, json=make_body())

    assert response.status_code == status
    assert response.json()["code"] == code
    assert "internal snapshot detail" not in response.text
    assert "internal database configuration" not in response.text
    assert "Traceback" not in response.text
    service.evaluate_trip.assert_called_once()
