"""M7-H4-B tests for V2 HTTP terrain composition safety."""

from unittest.mock import Mock

import httpx

from routevalue.api.terrain_v2_service import TerrainV2EvaluationService
from routevalue.api.v2_trip_evaluations import (
    get_profile_driven_trip_evaluation_service,
)
from routevalue.application.ports import (
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.infrastructure.routing.google_routes import (
    GoogleRoutesRouteProvider,
)
from routevalue.main import create_app


def _compose() -> TerrainV2EvaluationService:
    result = get_profile_driven_trip_evaluation_service(
        preferences_repository=Mock(spec=UserPreferencesRepository),
        saved_vehicle_repository=Mock(spec=SavedVehicleRepository),
        api_key="synthetic-test-key",
        client=Mock(spec=httpx.Client),
    )

    assert isinstance(result, TerrainV2EvaluationService)
    return result


def test_default_dependency_returns_terrain_compatible_service() -> None:
    result = _compose()

    assert isinstance(result, TerrainV2EvaluationService)


def test_default_dependency_does_not_enable_terrain_acquisition() -> None:
    result = _compose()

    assert result.application_service.terrain_acquisition_service is None


def test_default_dependency_preserves_authenticated_profile_resolution() -> None:
    preferences = Mock(spec=UserPreferencesRepository)
    vehicles = Mock(spec=SavedVehicleRepository)

    result = get_profile_driven_trip_evaluation_service(
        preferences_repository=preferences,
        saved_vehicle_repository=vehicles,
        api_key="synthetic-test-key",
        client=Mock(spec=httpx.Client),
    )

    assert isinstance(result, TerrainV2EvaluationService)

    resolver = result.application_service.profile_resolution_service

    assert resolver.preferences_repository is preferences
    assert resolver.saved_vehicle_repository is vehicles


def test_default_dependency_retains_existing_route_provider() -> None:
    result = _compose()

    assert isinstance(
        result.application_service.route_provider,
        GoogleRoutesRouteProvider,
    )


def test_v2_http_response_schema_is_unchanged() -> None:
    openapi = create_app().openapi()

    operation = openapi["paths"]["/api/v2/trip-evaluations"]["post"]

    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]

    assert schema["$ref"] == ("#/components/schemas/V2TripEvaluationResponse")


def test_v1_endpoint_still_exists() -> None:
    openapi = create_app().openapi()

    assert "/trip-evaluations" in openapi["paths"]
    assert "post" in openapi["paths"]["/trip-evaluations"]


def test_composition_does_not_execute_provider_requests() -> None:
    client = Mock(spec=httpx.Client)
    preferences = Mock(spec=UserPreferencesRepository)
    vehicles = Mock(spec=SavedVehicleRepository)

    result = get_profile_driven_trip_evaluation_service(
        preferences_repository=preferences,
        saved_vehicle_repository=vehicles,
        api_key="synthetic-test-key",
        client=client,
    )

    assert isinstance(result, TerrainV2EvaluationService)

    client.post.assert_not_called()
    preferences.get_preferences.assert_not_called()
    vehicles.get_vehicle.assert_not_called()
