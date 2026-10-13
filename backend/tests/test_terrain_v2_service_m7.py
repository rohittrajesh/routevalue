"""M7-H3 tests for the HTTP-compatible authenticated terrain adapter."""

from decimal import Decimal
from typing import cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from routevalue.api.terrain_v2_service import TerrainV2EvaluationService
from routevalue.application.authenticated_terrain_trip import (
    AuthenticatedTerrainTripService,
)
from routevalue.application.models import (
    ResolvedLocation,
    RouteSearchRequest,
    TripEvaluationResult,
)
from routevalue.domain.decision_engine import decide_route
from routevalue.domain.identity import SavedVehicleId, UserId

_USER_ID = UserId(value=UUID("00000000-0000-4000-8000-000000000001"))
_VEHICLE_ID = SavedVehicleId(value=UUID("00000000-0000-4000-8000-000000000002"))


def _request() -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=ResolvedLocation(
            display_name="Origin",
            latitude=32.0,
            longitude=-117.0,
        ),
        destination=ResolvedLocation(
            display_name="Destination",
            latitude=32.01,
            longitude=-117.01,
        ),
    )


def _trip() -> TripEvaluationResult:
    return TripEvaluationResult(
        route_evaluations=(),
        decision=decide_route(
            (),
            value_of_time_per_hour=Decimal(0),
            candidate_count=0,
            missing_data_present=False,
        ),
    )


def _adapter() -> tuple[TerrainV2EvaluationService, Mock, TripEvaluationResult]:
    application = Mock(spec=AuthenticatedTerrainTripService)
    trip = _trip()
    application.evaluate_trip.return_value.evaluation.trip = trip

    return (
        TerrainV2EvaluationService(
            application_service=cast(
                AuthenticatedTerrainTripService,
                application,
            )
        ),
        application,
        trip,
    )


def test_adapter_returns_existing_trip_result_type() -> None:
    adapter, _, expected = _adapter()

    actual = adapter.evaluate_trip(
        _USER_ID,
        _request(),
        fuel_price_per_gallon=Decimal("4.50"),
    )

    assert isinstance(actual, TripEvaluationResult)
    assert actual is expected


def test_gasoline_arguments_are_forwarded_unchanged() -> None:
    adapter, application, _ = _adapter()
    request = _request()

    adapter.evaluate_trip(
        _USER_ID,
        request,
        fuel_price_per_gallon=Decimal("4.50"),
        requested_vehicle_id=_VEHICLE_ID,
    )

    application.evaluate_trip.assert_called_once_with(
        _USER_ID,
        request,
        fuel_price_per_gallon=Decimal("4.50"),
        price_per_kilowatt_hour=None,
        requested_vehicle_id=_VEHICLE_ID,
    )


def test_electric_arguments_are_forwarded_unchanged() -> None:
    adapter, application, _ = _adapter()
    request = _request()

    adapter.evaluate_trip(
        _USER_ID,
        request,
        price_per_kilowatt_hour=Decimal("0.30"),
    )

    application.evaluate_trip.assert_called_once_with(
        _USER_ID,
        request,
        fuel_price_per_gallon=None,
        price_per_kilowatt_hour=Decimal("0.30"),
        requested_vehicle_id=None,
    )


def test_known_zero_price_is_not_replaced_with_none() -> None:
    adapter, application, _ = _adapter()

    adapter.evaluate_trip(
        _USER_ID,
        _request(),
        price_per_kilowatt_hour=Decimal(0),
    )

    assert application.evaluate_trip.call_args.kwargs["price_per_kilowatt_hour"] == Decimal(0)


def test_application_validation_failure_is_not_swallowed() -> None:
    adapter, application, _ = _adapter()
    application.evaluate_trip.side_effect = ValueError("synthetic invalid request")

    with pytest.raises(ValueError, match="synthetic invalid request"):
        adapter.evaluate_trip(
            _USER_ID,
            _request(),
            fuel_price_per_gallon=Decimal(4),
        )


def test_adapter_does_not_call_application_during_construction() -> None:
    _, application, _ = _adapter()

    application.evaluate_trip.assert_not_called()


def test_repeated_calls_return_the_same_trip_result() -> None:
    adapter, application, expected = _adapter()
    request = _request()

    first = adapter.evaluate_trip(
        _USER_ID,
        request,
        fuel_price_per_gallon=Decimal(4),
    )
    second = adapter.evaluate_trip(
        _USER_ID,
        request,
        fuel_price_per_gallon=Decimal(4),
    )

    assert first is expected
    assert second is expected
    assert application.evaluate_trip.call_count == 2
