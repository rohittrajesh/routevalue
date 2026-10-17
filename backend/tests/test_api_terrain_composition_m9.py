"""V2 API composition tests for matching routing and elevation modes."""

from unittest.mock import MagicMock

import httpx
import pytest

from routevalue.api import v2_trip_evaluations as api
from routevalue.api.terrain_v2_acquisition import TERRAIN_SINGLE_PROCESS_DEV_ENV
from routevalue.api.terrain_v2_service import TerrainV2EvaluationService
from routevalue.infrastructure.elevation.safety import TERRAIN_LIVE_ENABLED_ENV
from routevalue.infrastructure.routing.google_routes import GoogleRoutesRouteProvider


@pytest.mark.parametrize(
    ("enabled", "expected_quality"),
    [
        (False, "OVERVIEW"),
        (True, "HIGH_QUALITY"),
    ],
)
def test_v2_composition_pairs_routing_and_elevation_modes(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    expected_quality: str,
) -> None:
    monkeypatch.setenv(
        TERRAIN_LIVE_ENABLED_ENV,
        "1" if enabled else "0",
    )
    monkeypatch.setenv(TERRAIN_SINGLE_PROCESS_DEV_ENV, "1")

    monkeypatch.setattr(
        api,
        "build_lazy_eia_pricing_dependencies",
        lambda **kwargs: (None, None),
    )

    with httpx.Client() as client:
        service = api.get_profile_driven_trip_evaluation_service(
            preferences_repository=MagicMock(),
            saved_vehicle_repository=MagicMock(),
            api_key="test-key",
            client=client,
        )

    assert isinstance(service, TerrainV2EvaluationService)

    application_service = service.application_service
    provider = application_service.route_provider

    assert isinstance(provider, GoogleRoutesRouteProvider)
    assert provider._polyline_quality == expected_quality

    if enabled:
        assert application_service.terrain_acquisition_service is not None
    else:
        assert application_service.terrain_acquisition_service is None


def test_v2_composition_rejects_unconfirmed_live_elevation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TERRAIN_LIVE_ENABLED_ENV, "1")
    monkeypatch.delenv(TERRAIN_SINGLE_PROCESS_DEV_ENV, raising=False)

    with (
        httpx.Client() as client,
        pytest.raises(ValueError, match="single-process development"),
    ):
        api.get_profile_driven_trip_evaluation_service(
            preferences_repository=MagicMock(),
            saved_vehicle_repository=MagicMock(),
            api_key="test-key",
            client=client,
        )
