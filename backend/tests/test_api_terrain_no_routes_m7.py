"""M7 HTTP regression tests for an empty routing result."""

from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from routevalue.api.terrain_v2_service import TerrainV2EvaluationService
from routevalue.api.user_identity import get_authenticated_user
from routevalue.api.v2_trip_evaluations import (
    get_profile_driven_trip_evaluation_service,
)
from routevalue.application.authenticated_terrain_trip import (
    NoRoutesAvailableError,
)
from routevalue.application.identity import AuthenticatedUser
from routevalue.domain.identity import UserId
from routevalue.main import create_app

_PATH = "/api/v2/trip-evaluations"

_USER_ID = UserId(value=UUID("00000000-0000-4000-8000-000000000001"))


def _body(*, electric: bool) -> dict[str, object]:
    body: dict[str, object] = {
        "origin": {
            "display_name": "Origin",
            "latitude": 32.0,
            "longitude": -117.0,
        },
        "destination": {
            "display_name": "Destination",
            "latitude": 32.1,
            "longitude": -117.1,
        },
    }

    if electric:
        body["electricity"] = {
            "price_per_kilowatt_hour": "0.30",
        }
    else:
        body["gasoline"] = {
            "fuel_price_per_gallon": "4.50",
        }

    return body


@pytest.mark.parametrize("electric", [False, True])
def test_no_routes_returns_safe_502_for_both_powertrains(
    electric: bool,
) -> None:
    service = Mock(spec=TerrainV2EvaluationService)
    service.evaluate_trip.side_effect = NoRoutesAvailableError(
        "internal routing details must remain private"
    )

    app = create_app()

    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(user_id=_USER_ID)
    app.dependency_overrides[get_profile_driven_trip_evaluation_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            _PATH,
            json=_body(electric=electric),
        )

    assert response.status_code == 502
    assert response.json() == {
        "code": "routing_response_invalid",
        "detail": "The routing service returned no usable routes.",
    }
    assert "internal routing details" not in response.text
    service.evaluate_trip.assert_called_once()

    args, kwargs = service.evaluate_trip.call_args

    assert args[0] == _USER_ID
    assert kwargs["requested_vehicle_id"] is None

    if electric:
        assert kwargs["price_per_kilowatt_hour"] is not None
        assert kwargs["fuel_price_per_gallon"] is None
    else:
        assert kwargs["fuel_price_per_gallon"] is not None
        assert kwargs["price_per_kilowatt_hour"] is None
