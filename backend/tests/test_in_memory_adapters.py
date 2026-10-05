from decimal import Decimal

from routevalue.application.models import ResolvedLocation, RouteSearchRequest
from routevalue.domain.models import EnergyEstimate, RouteCandidate
from routevalue.infrastructure.in_memory import (
    InMemoryEnergyCostEstimator,
    InMemoryRouteProvider,
)


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


def test_in_memory_route_provider_preserves_configured_order() -> None:
    first_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    second_route = RouteCandidate(
        distance_meters=12_000,
        duration_seconds=800,
        toll_cost=Decimal("2.00"),
    )

    provider = InMemoryRouteProvider(
        (
            first_route,
            second_route,
        )
    )

    routes = provider.get_routes(_route_search_request())

    assert tuple(routes) == (
        first_route,
        second_route,
    )


def test_in_memory_energy_estimator_returns_configured_estimate() -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    estimate = EnergyEstimate(cost=Decimal("2.50"))

    estimator = InMemoryEnergyCostEstimator(
        {
            route: estimate,
        }
    )

    assert estimator.estimate_energy(route) == estimate


def test_in_memory_energy_estimator_returns_none_for_unknown_route() -> None:
    configured_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    unknown_route = RouteCandidate(
        distance_meters=12_000,
        duration_seconds=800,
        toll_cost=Decimal(0),
    )

    estimator = InMemoryEnergyCostEstimator(
        {
            configured_route: EnergyEstimate(cost=Decimal("2.50")),
        }
    )

    assert estimator.estimate_energy(unknown_route) is None
