"""M8-R3 geographic pricing failure HTTP regression tests."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_trip_evaluations import (
    get_profile_driven_trip_evaluation_service,
)
from routevalue.application.gasoline_price_geography import (
    PricingGeographyUnavailableError,
    PricingGeographyUnavailableReason,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.domain.identity import UserId
from routevalue.main import create_app

_PATH = "/api/v2/trip-evaluations"


def make_body() -> dict[str, object]:
    return {
        "origin": {
            "display_name": "Origin",
            "latitude": 34.0,
            "longitude": -118.0,
        },
        "destination": {
            "display_name": "Destination",
            "latitude": 34.1,
            "longitude": -118.1,
        },
    }


@pytest.mark.parametrize(
    "reason",
    [
        PricingGeographyUnavailableReason.OUTSIDE_SUPPORTED_COUNTRY,
        PricingGeographyUnavailableReason.JURISDICTION_UNKNOWN,
    ],
)
def test_unavailable_geography_returns_safe_409(
    reason: PricingGeographyUnavailableReason,
) -> None:
    user_id = UserId(value=uuid4())
    service = Mock()

    service.evaluate_trip.side_effect = PricingGeographyUnavailableError(reason)

    app = create_app()

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=user_id)
    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(_PATH, json=make_body())

    assert response.status_code == 409
    assert response.json()["code"] == "gasoline_price_unavailable"
    assert "manual gasoline price" in response.json()["detail"]
    assert "Traceback" not in response.text
    assert "DATABASE_URL" not in response.text
    service.evaluate_trip.assert_called_once()
