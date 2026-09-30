"""Application ports for RouteValue."""

from collections.abc import Sequence
from typing import Protocol

from routevalue.application.models import RouteSearchRequest
from routevalue.domain.models import EnergyEstimate, RouteCandidate


class RouteProvider(Protocol):
    """Provides normalized route candidates to the application layer."""

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[RouteCandidate]:
        """Return normalized candidate routes in stable provider order."""
        ...


class EnergyCostEstimator(Protocol):
    """Provides a monetary energy-cost estimate for a normalized route."""

    def estimate_energy(
        self,
        route: RouteCandidate,
    ) -> EnergyEstimate | None:
        """Return the route's energy estimate, or None when unavailable."""
        ...
