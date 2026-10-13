"""Safe composition of authenticated terrain-aware V2 evaluation."""

from routevalue.api.terrain_v2_service import TerrainV2EvaluationService
from routevalue.application.authenticated_terrain_trip import (
    AuthenticatedTerrainTripService,
)
from routevalue.application.ports import (
    RouteProvider,
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.application.profile_resolution import ProfileResolutionService
from routevalue.application.terrain_acquisition import TerrainAcquisitionService


def build_terrain_v2_evaluation_service(
    *,
    preferences_repository: UserPreferencesRepository,
    saved_vehicle_repository: SavedVehicleRepository,
    route_provider: RouteProvider,
    terrain_acquisition_service: TerrainAcquisitionService | None = None,
) -> TerrainV2EvaluationService:
    """Build the authenticated V2 service with optional terrain acquisition.

    By default, no terrain service exists, so elevation requests cannot
    be made.

    A supplied acquisition service retains responsibility for its own
    enablement flag, budget, and provider configuration.

    Authentication and saved-vehicle ownership remain the responsibility
    of the existing API identity and profile-resolution boundaries.
    """

    profile_resolution_service = ProfileResolutionService(
        preferences_repository=preferences_repository,
        saved_vehicle_repository=saved_vehicle_repository,
    )

    application_service = AuthenticatedTerrainTripService(
        profile_resolution_service=profile_resolution_service,
        route_provider=route_provider,
        terrain_acquisition_service=terrain_acquisition_service,
    )

    return TerrainV2EvaluationService(
        application_service=application_service,
    )
