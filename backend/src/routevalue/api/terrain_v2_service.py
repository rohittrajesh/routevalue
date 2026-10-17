"""HTTP-compatible boundary for authenticated terrain-aware V2 trips."""

from dataclasses import dataclass

from routevalue.application.authenticated_terrain_trip import (
    AuthenticatedTerrainTripOutcome,
    AuthenticatedTerrainTripService,
)
from routevalue.application.models import RouteSearchRequest, TripEvaluationResult
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.units import MoneyPerGallon, MoneyPerKilowattHour


@dataclass(frozen=True, slots=True)
class TerrainV2EvaluationService:
    """Expose the established V2 evaluation contract using terrain internally.

    Preserve the existing HTTP response model. Terrain diagnostics are
    intentionally not exposed through this compatibility adapter yet.

    Terrain acquisition remains disabled unless an explicitly configured
    application service supplies a guarded acquisition dependency.
    """

    application_service: AuthenticatedTerrainTripService

    def evaluate_trip(
        self,
        user_id: UserId,
        request: RouteSearchRequest,
        *,
        fuel_price_per_gallon: MoneyPerGallon | None = None,
        price_per_kilowatt_hour: MoneyPerKilowattHour | None = None,
        requested_vehicle_id: SavedVehicleId | None = None,
    ) -> TripEvaluationResult:
        """Return the same application result expected by the V2 endpoint."""

        outcome = self.application_service.evaluate_trip(
            user_id,
            request,
            fuel_price_per_gallon=fuel_price_per_gallon,
            price_per_kilowatt_hour=price_per_kilowatt_hour,
            requested_vehicle_id=requested_vehicle_id,
        )

        return outcome.evaluation.trip

    def evaluate_trip_with_diagnostics(
        self,
        user_id: UserId,
        request: RouteSearchRequest,
        *,
        fuel_price_per_gallon: MoneyPerGallon | None = None,
        price_per_kilowatt_hour: MoneyPerKilowattHour | None = None,
        requested_vehicle_id: SavedVehicleId | None = None,
    ) -> AuthenticatedTerrainTripOutcome:
        """Return the full authenticated evaluation and terrain diagnostics.

        Run the application evaluation exactly once. This preserves
        the actual acquisition, geometry, and energy decisions.
        """
        return self.application_service.evaluate_trip(
            user_id,
            request,
            fuel_price_per_gallon=fuel_price_per_gallon,
            price_per_kilowatt_hour=price_per_kilowatt_hour,
            requested_vehicle_id=requested_vehicle_id,
        )
