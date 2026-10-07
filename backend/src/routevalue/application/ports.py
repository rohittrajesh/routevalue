"""Application ports for RouteValue."""

from collections.abc import Sequence
from typing import Protocol

from routevalue.application.identity import VerifiedExternalIdentity
from routevalue.application.models import (
    ProvidedRoute,
    RouteSearchRequest,
    VehicleCatalogConfiguration,
    VehicleSpecificationLookupResult,
)
from routevalue.application.preferences import UserPreferences
from routevalue.domain.identity import UserId
from routevalue.domain.models import EnergyEstimate, RouteCandidate


class RouteProvider(Protocol):
    """Provides normalized routes to the application layer."""

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[ProvidedRoute]:
        """Return normalized provided routes in stable provider order."""
        ...


class EnergyCostEstimator(Protocol):
    """Provides a monetary energy-cost estimate for a normalized route."""

    def estimate_energy(
        self,
        route: RouteCandidate,
    ) -> EnergyEstimate | None:
        """Return the route's energy estimate, or None when unavailable."""
        ...


class VehicleSpecificationProvider(Protocol):
    """Provides provider-neutral vehicle catalog discovery and specifications."""

    def list_years(self) -> Sequence[int]:
        """Return available model years in deterministic order."""
        ...

    def list_makes(
        self,
        *,
        year: int,
    ) -> Sequence[str]:
        """Return available makes for a model year in deterministic order."""
        ...

    def list_models(
        self,
        *,
        year: int,
        make: str,
    ) -> Sequence[str]:
        """Return available models for a year and make in deterministic order."""
        ...

    def list_configurations(
        self,
        *,
        year: int,
        make: str,
        model: str,
    ) -> Sequence[VehicleCatalogConfiguration]:
        """Return selectable configurations in deterministic order."""
        ...

    def get_specification(
        self,
        configuration: VehicleCatalogConfiguration,
    ) -> VehicleSpecificationLookupResult:
        """Resolve one catalog configuration to a normalized specification outcome."""
        ...


class AuthenticationVerifier(Protocol):
    """Verifies credentials without exposing authentication-provider details."""

    def verify_token(
        self,
        token: str,
    ) -> VerifiedExternalIdentity:
        """Return a verified identity or raise an authentication error."""
        ...


class UserIdentityRepository(Protocol):
    """Maps verified external identities to permanent RouteValue users."""

    def get_or_create_user_id(
        self,
        identity: VerifiedExternalIdentity,
    ) -> UserId:
        """Atomically return the stable internal user for an external identity."""
        ...


class UserPreferencesRepository(Protocol):
    """Persists personalization settings for internal RouteValue users."""

    def get_preferences(
        self,
        user_id: UserId,
    ) -> UserPreferences:
        """Return persisted preferences, using unset values when no row exists."""
        ...

    def save_preferences(
        self,
        user_id: UserId,
        preferences: UserPreferences,
    ) -> UserPreferences:
        """Persist and return the complete preference state."""
        ...
