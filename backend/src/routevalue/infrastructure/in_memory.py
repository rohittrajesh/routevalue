"""Temporary in-memory adapters for RouteValue application ports."""

from collections.abc import Mapping, Sequence

from routevalue.application.models import ProvidedRoute, RouteSearchRequest
from routevalue.domain.models import EnergyEstimate, RouteCandidate


class InMemoryRouteProvider:
    """Return a controlled set of normalized routes from memory."""

    def __init__(
        self,
        routes: Sequence[RouteCandidate | ProvidedRoute],
    ) -> None:
        self._routes = tuple(
            route if isinstance(route, ProvidedRoute) else ProvidedRoute(route=route)
            for route in routes
        )

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[ProvidedRoute]:
        """Return routes in the exact configured order."""

        return self._routes


class InMemoryEnergyCostEstimator:
    """Return controlled energy estimates from memory."""

    def __init__(
        self,
        estimates: Mapping[RouteCandidate, EnergyEstimate | None],
    ) -> None:
        self._estimates = dict(estimates)

    def estimate_energy(
        self,
        route: RouteCandidate,
    ) -> EnergyEstimate | None:
        """Return the configured estimate, or None when unavailable."""

        return self._estimates.get(route)
