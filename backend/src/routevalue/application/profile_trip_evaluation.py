"""Application orchestration for authenticated profile-driven trips."""

from collections.abc import Callable
from dataclasses import dataclass

from routevalue.application.gasoline_evaluation import (
    GasolineEvaluationContext,
    build_gasoline_evaluation_context,
)
from routevalue.application.models import (
    RouteSearchRequest,
    TripEvaluationResult,
)
from routevalue.application.ports import (
    EnergyCostEstimator,
    RouteProvider,
)
from routevalue.application.profile_resolution import (
    ProfileResolutionService,
)
from routevalue.application.trip_evaluation import (
    TripEvaluationOrchestrator,
)
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.units import MoneyPerGallon

type GasolineEstimatorFactory = Callable[
    [GasolineEvaluationContext],
    EnergyCostEstimator,
]


@dataclass(frozen=True, slots=True)
class ProfileDrivenTripEvaluationService:
    """Evaluate trips using stored personalization and an owned vehicle."""

    profile_resolution_service: ProfileResolutionService
    route_provider: RouteProvider
    gasoline_estimator_factory: GasolineEstimatorFactory

    def evaluate_trip(
        self,
        user_id: UserId,
        request: RouteSearchRequest,
        *,
        fuel_price_per_gallon: MoneyPerGallon,
        requested_vehicle_id: SavedVehicleId | None = None,
    ) -> TripEvaluationResult:
        """Evaluate a trip using the user's persisted evaluation profile.

        Resolve all required profile data before acquiring routes.
        Preserve the existing authoritative decision engine.
        """

        profile = self.profile_resolution_service.resolve_profile(
            user_id,
            requested_vehicle_id=requested_vehicle_id,
        )

        gasoline_context = build_gasoline_evaluation_context(
            profile.saved_vehicle,
            fuel_price_per_gallon=fuel_price_per_gallon,
        )

        energy_estimator = self.gasoline_estimator_factory(gasoline_context)

        orchestrator = TripEvaluationOrchestrator(
            route_provider=self.route_provider,
            energy_cost_estimator=energy_estimator,
        )

        return orchestrator.evaluate_trip(
            request,
            value_of_time_per_hour=profile.value_of_time_per_hour,
        )
