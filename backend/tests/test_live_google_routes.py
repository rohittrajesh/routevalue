import os

import httpx
import pytest

from routevalue.application.models import ResolvedLocation, RouteSearchRequest
from routevalue.infrastructure.routing.google_routes import GoogleRoutesRouteProvider

_RUN_LIVE_GOOGLE_ROUTES = os.getenv("RUN_LIVE_GOOGLE_ROUTES") == "1"


@pytest.mark.skipif(
    not _RUN_LIVE_GOOGLE_ROUTES,
    reason="set RUN_LIVE_GOOGLE_ROUTES=1 to run the live Google Routes smoke test",
)
def test_google_routes_live_smoke() -> None:
    api_key = os.getenv("GOOGLE_ROUTES_API_KEY")

    assert api_key is not None
    assert api_key.strip()

    with httpx.Client(timeout=15.0) as client:
        provider = GoogleRoutesRouteProvider(
            api_key=api_key,
            client=client,
        )

        provided_routes = provider.get_routes(
            RouteSearchRequest(
                origin=ResolvedLocation(
                    display_name="UC San Diego",
                    latitude=32.8801,
                    longitude=-117.2340,
                ),
                destination=ResolvedLocation(
                    display_name="San Diego International Airport",
                    latitude=32.7338,
                    longitude=-117.1933,
                ),
            )
        )

    assert provided_routes

    for provided_route in provided_routes:
        route = provided_route.route

        assert route.distance_meters > 0
        assert route.duration_seconds > 0
        assert route.toll_cost is None or route.toll_cost >= 0

        assert provided_route.geometry is not None
        assert len(provided_route.geometry.points) >= 2
