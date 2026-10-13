"""M7 no-route failure classification regression."""

from decimal import Decimal
from typing import cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from routevalue.application.authenticated_terrain_trip import (
    AuthenticatedTerrainTripService,
    NoRoutesAvailableError,
)
from routevalue.application.models import ResolvedLocation, RouteSearchRequest
from routevalue.application.ports import RouteProvider
from routevalue.application.profile_resolution import (
    ProfileResolutionService,
    ResolvedEvaluationProfile,
)
from routevalue.domain.identity import UserId
from routevalue.domain.models import (
    GasolineGrade,
    GasolineVehicleSpecification,
)


def test_empty_route_provider_raises_specific_error() -> None:
    resolver = Mock(spec=ProfileResolutionService)
    saved_vehicle = Mock()
    saved_vehicle.specification = GasolineVehicleSpecification(
        combined_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
    )

    resolver.resolve_profile.return_value = ResolvedEvaluationProfile(
        value_of_time_per_hour=Decimal(20),
        saved_vehicle=saved_vehicle,
    )

    routing = Mock(spec=RouteProvider)
    routing.get_routes.return_value = ()

    service = AuthenticatedTerrainTripService(
        profile_resolution_service=cast(ProfileResolutionService, resolver),
        route_provider=cast(RouteProvider, routing),
    )

    request = RouteSearchRequest(
        origin=ResolvedLocation("Origin", 32.0, -117.0),
        destination=ResolvedLocation("Destination", 32.1, -117.1),
    )

    with pytest.raises(NoRoutesAvailableError, match="no candidate routes"):
        service.evaluate_trip(
            UserId(value=UUID("00000000-0000-4000-8000-000000000001")),
            request,
            fuel_price_per_gallon=Decimal("4.50"),
        )

    routing.get_routes.assert_called_once_with(request)
