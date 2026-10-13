"""M7-H4-A tests for safe V2 terrain dependency composition."""

from unittest.mock import Mock

from routevalue.api.terrain_v2_composition import (
    build_terrain_v2_evaluation_service,
)
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


def _build(
    *,
    terrain_service: TerrainAcquisitionService | None = None,
) -> TerrainV2EvaluationService:
    return build_terrain_v2_evaluation_service(
        preferences_repository=Mock(spec=UserPreferencesRepository),
        saved_vehicle_repository=Mock(spec=SavedVehicleRepository),
        route_provider=Mock(spec=RouteProvider),
        terrain_acquisition_service=terrain_service,
    )


def test_factory_returns_http_compatible_service() -> None:
    result = _build()

    assert isinstance(result, TerrainV2EvaluationService)
    assert isinstance(
        result.application_service,
        AuthenticatedTerrainTripService,
    )


def test_default_terrain_acquisition_is_absent() -> None:
    result = _build()

    assert result.application_service.terrain_acquisition_service is None


def test_factory_preserves_supplied_dependencies() -> None:
    preferences = Mock(spec=UserPreferencesRepository)
    vehicles = Mock(spec=SavedVehicleRepository)
    routing = Mock(spec=RouteProvider)

    result = build_terrain_v2_evaluation_service(
        preferences_repository=preferences,
        saved_vehicle_repository=vehicles,
        route_provider=routing,
    )

    application = result.application_service
    resolver = application.profile_resolution_service

    assert isinstance(resolver, ProfileResolutionService)
    assert resolver.preferences_repository is preferences
    assert resolver.saved_vehicle_repository is vehicles
    assert application.route_provider is routing


def test_explicit_terrain_service_is_preserved() -> None:
    terrain_service = Mock(spec=TerrainAcquisitionService)

    result = _build(
        terrain_service=terrain_service,
    )

    assert result.application_service.terrain_acquisition_service is terrain_service


def test_factory_does_not_invoke_external_dependencies() -> None:
    preferences = Mock(spec=UserPreferencesRepository)
    vehicles = Mock(spec=SavedVehicleRepository)
    routing = Mock(spec=RouteProvider)
    terrain = Mock(spec=TerrainAcquisitionService)

    build_terrain_v2_evaluation_service(
        preferences_repository=preferences,
        saved_vehicle_repository=vehicles,
        route_provider=routing,
        terrain_acquisition_service=terrain,
    )

    preferences.assert_not_called()
    vehicles.assert_not_called()
    routing.assert_not_called()
    terrain.assert_not_called()
    terrain.acquire_routes.assert_not_called()


def test_repeated_composition_produces_separate_service_instances() -> None:
    first = _build()
    second = _build()

    assert first is not second
    assert first.application_service is not second.application_service


def test_no_hidden_configuration_is_required_for_composition() -> None:
    # Construction does not access environment variables, API keys,
    # routing providers, elevation providers, or databases.
    result = _build()

    assert isinstance(result, TerrainV2EvaluationService)
    assert result.application_service.terrain_acquisition_service is None
