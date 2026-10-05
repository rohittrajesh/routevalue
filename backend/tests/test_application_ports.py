from collections.abc import Sequence
from decimal import Decimal

import pytest

from routevalue.application.models import ResolvedLocation, RouteSearchRequest
from routevalue.application.ports import EnergyCostEstimator, RouteProvider
from routevalue.domain.models import EnergyEstimate, RouteCandidate


class FakeRouteProvider:
    def __init__(self, routes: Sequence[RouteCandidate]) -> None:
        self._routes = tuple(routes)
        self.requests: list[RouteSearchRequest] = []

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[RouteCandidate]:
        self.requests.append(request)
        return self._routes


class FakeEnergyCostEstimator:
    def __init__(self, estimate: EnergyEstimate | None) -> None:
        self._estimate = estimate
        self.routes: list[RouteCandidate] = []

    def estimate_energy(
        self,
        route: RouteCandidate,
    ) -> EnergyEstimate | None:
        self.routes.append(route)
        return self._estimate


def get_routes_from_provider(
    provider: RouteProvider,
    request: RouteSearchRequest,
) -> Sequence[RouteCandidate]:
    return provider.get_routes(request)


def get_energy_estimate(
    estimator: EnergyCostEstimator,
    route: RouteCandidate,
) -> EnergyEstimate | None:
    return estimator.estimate_energy(route)


def _route_search_request() -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=ResolvedLocation(
            display_name="Origin",
            latitude=32.88,
            longitude=-117.23,
        ),
        destination=ResolvedLocation(
            display_name="Destination",
            latitude=32.88,
            longitude=-117.23,
        ),
    )


def test_fake_route_provider_returns_controlled_routes_in_stable_order() -> None:
    first_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    second_route = RouteCandidate(
        distance_meters=12_000,
        duration_seconds=800,
        toll_cost=Decimal("2.50"),
    )
    request = _route_search_request()
    provider = FakeRouteProvider([first_route, second_route])

    routes = get_routes_from_provider(provider, request)

    assert routes == (first_route, second_route)
    assert provider.requests == [request]


@pytest.mark.parametrize(
    "display_name",
    [
        "",
        "   ",
    ],
)
def test_resolved_location_rejects_blank_display_name(
    display_name: str,
) -> None:
    with pytest.raises(ValueError, match="display_name cannot be blank"):
        ResolvedLocation(
            display_name=display_name,
            latitude=32.88,
            longitude=-117.23,
        )


@pytest.mark.parametrize(
    "estimate",
    [
        EnergyEstimate(cost=Decimal("1.25")),
        None,
    ],
)
def test_fake_energy_cost_estimator_returns_controlled_result(
    estimate: EnergyEstimate | None,
) -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    estimator = FakeEnergyCostEstimator(estimate)

    result = get_energy_estimate(estimator, route)

    assert result == estimate
    assert estimator.routes == [route]
