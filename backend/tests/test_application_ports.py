from collections.abc import Sequence
from decimal import Decimal

import pytest

from routevalue.application.models import RouteSearchRequest
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
    request = RouteSearchRequest(
        origin="Origin",
        destination="Destination",
    )
    provider = FakeRouteProvider([first_route, second_route])

    routes = get_routes_from_provider(provider, request)

    assert routes == (first_route, second_route)
    assert provider.requests == [request]


@pytest.mark.parametrize(
    ("origin", "destination", "message"),
    [
        ("", "Destination", "origin cannot be blank"),
        ("Origin", "   ", "destination cannot be blank"),
    ],
)
def test_route_search_request_rejects_blank_endpoint(
    origin: str,
    destination: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        RouteSearchRequest(
            origin=origin,
            destination=destination,
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
