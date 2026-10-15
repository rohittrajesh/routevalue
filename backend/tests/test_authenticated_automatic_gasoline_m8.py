"""M8-R2 automatic gasoline pricing tests for authenticated trip evaluation."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import Mock
from uuid import UUID

import pytest

from routevalue.application.authenticated_terrain_trip import (
    AuthenticatedTerrainTripService,
)
from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteSearchRequest,
    VehicleCatalogConfiguration,
)
from routevalue.application.profile_resolution import (
    ProfileResolutionService,
    ResolvedEvaluationProfile,
)
from routevalue.application.profile_trip_evaluation import EnergyInputMismatchError
from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.application.terrain_normalization import NormalizedTerrainProfile
from routevalue.application.terrain_trip_evaluation import (
    TerrainTripEvaluationOrchestrator,
    TerrainTripEvaluationOutcome,
)
from routevalue.domain.gasoline_price_metadata import GasolineMarketMetadata
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
    GasolineVehicleSpecification,
    RouteCandidate,
)
from routevalue.domain.units import MoneyPerHour
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
)

USER_ID = UserId(value=UUID("00000000-0000-4000-8000-000000000001"))
VEHICLE_ID = SavedVehicleId(value=UUID("00000000-0000-4000-8000-000000000002"))
OBSERVED_AT = datetime(2026, 10, 12, tzinfo=UTC)


class FakeRoutes:
    def __init__(self) -> None:
        self.calls = 0

    def get_routes(self, request: RouteSearchRequest) -> Sequence[ProvidedRoute]:
        self.calls += 1
        return (
            ProvidedRoute(
                route=RouteCandidate(1609, 300, Decimal(0)),
            ),
            ProvidedRoute(
                route=RouteCandidate(3218, 450, Decimal(0)),
            ),
        )


class QuoteResolver:
    def __init__(self, quote: GasolinePriceQuote) -> None:
        self.quote = quote
        self.calls: list[tuple[ResolvedLocation, GasolineGrade]] = []

    def __call__(
        self,
        origin: ResolvedLocation,
        grade: GasolineGrade,
    ) -> GasolinePriceQuote:
        self.calls.append((origin, grade))
        return self.quote


def make_request() -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=ResolvedLocation("Origin", 34.0, -118.0),
        destination=ResolvedLocation("Destination", 34.1, -118.1),
    )


def make_vehicle(
    *,
    electric: bool = False,
    grade: GasolineGrade = GasolineGrade.REGULAR,
) -> SavedVehicle:
    specification = (
        ElectricVehicleSpecification(
            combined_kwh_per_mile=Decimal("0.30"),
        )
        if electric
        else GasolineVehicleSpecification(
            combined_mpg=Decimal(30),
            fuel_grade=grade,
        )
    )
    timestamp = datetime(2026, 10, 13, tzinfo=UTC)

    return SavedVehicle(
        id=VEHICLE_ID,
        configuration=VehicleCatalogConfiguration(
            year=2025,
            make="Example",
            model="Test",
            configuration="Standard",
            source="test",
            source_id="example-1",
        ),
        specification=specification,
        specification_retrieved_at=timestamp,
        saved_at=timestamp,
    )


def make_quote(
    grade: GasolineGrade = GasolineGrade.REGULAR,
) -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal("6.227"),
        fuel_grade=grade,
        source=GasolinePriceSource.REGIONAL_MARKET,
        observed_at=OBSERVED_AT,
        market_metadata=GasolineMarketMetadata(
            provider="EIA",
            geography=EIA_CALIFORNIA_REGION.geography,
        ),
    )


def make_service(
    *,
    electric: bool = False,
    grade: GasolineGrade = GasolineGrade.REGULAR,
    automatic_resolver: Callable[[ResolvedLocation, GasolineGrade], GasolinePriceQuote]
    | None = None,
) -> tuple[AuthenticatedTerrainTripService, FakeRoutes, Mock]:
    profile_service = Mock(spec=ProfileResolutionService)
    profile_service.resolve_profile.return_value = ResolvedEvaluationProfile(
        value_of_time_per_hour=Decimal(15),
        saved_vehicle=make_vehicle(electric=electric, grade=grade),
    )

    routes = FakeRoutes()
    service = AuthenticatedTerrainTripService(
        profile_resolution_service=cast(ProfileResolutionService, profile_service),
        route_provider=routes,
        automatic_gasoline_price_resolver=automatic_resolver,
    )
    return service, routes, profile_service


def test_automatic_gasoline_evaluates_without_manual_price() -> None:
    resolver = QuoteResolver(make_quote())
    service, routes, profile = make_service(automatic_resolver=resolver)

    result = service.evaluate_trip(USER_ID, make_request())

    assert result.evaluation.trip.decision.eligible_count == 2
    assert routes.calls == 1
    assert resolver.calls == [(make_request().origin, GasolineGrade.REGULAR)]
    profile.resolve_profile.assert_called_once_with(USER_ID, requested_vehicle_id=None)


def test_automatic_market_quote_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quote = make_quote()
    resolver = QuoteResolver(quote)
    service, _, _ = make_service(automatic_resolver=resolver)

    captured: list[GasolinePriceQuote | None] = []
    original = TerrainTripEvaluationOrchestrator.evaluate_gasoline_trip

    def recording_evaluation(
        self: TerrainTripEvaluationOrchestrator,
        provided_routes: Sequence[ProvidedRoute],
        *,
        terrain_profiles: Sequence[NormalizedTerrainProfile | None],
        vehicle: GasolineVehicleSpecification,
        fuel_price_quote: GasolinePriceQuote | None,
        value_of_time_per_hour: MoneyPerHour,
    ) -> TerrainTripEvaluationOutcome:
        assert isinstance(fuel_price_quote, GasolinePriceQuote)
        captured.append(fuel_price_quote)
        return original(
            self,
            provided_routes,
            terrain_profiles=terrain_profiles,
            vehicle=vehicle,
            fuel_price_quote=fuel_price_quote,
            value_of_time_per_hour=value_of_time_per_hour,
        )

    monkeypatch.setattr(
        TerrainTripEvaluationOrchestrator,
        "evaluate_gasoline_trip",
        recording_evaluation,
    )

    service.evaluate_trip(USER_ID, make_request())

    assert captured == [quote]
    assert captured[0] is quote
    assert captured[0].source is GasolinePriceSource.REGIONAL_MARKET
    assert captured[0].observed_at == OBSERVED_AT
    assert captured[0].market_metadata == quote.market_metadata


def test_manual_price_bypasses_automatic_resolver() -> None:
    resolver = QuoteResolver(make_quote())
    service, routes, _ = make_service(automatic_resolver=resolver)

    result = service.evaluate_trip(
        USER_ID,
        make_request(),
        fuel_price_per_gallon=Decimal("4.50"),
    )

    assert result.evaluation.trip.decision.eligible_count == 2
    assert routes.calls == 1
    assert resolver.calls == []


def test_saved_vehicle_premium_grade_is_forwarded() -> None:
    resolver = QuoteResolver(make_quote(GasolineGrade.PREMIUM))
    service, _, _ = make_service(
        grade=GasolineGrade.PREMIUM,
        automatic_resolver=resolver,
    )

    service.evaluate_trip(USER_ID, make_request())

    assert resolver.calls == [(make_request().origin, GasolineGrade.PREMIUM)]


def test_wrong_market_grade_rejected_before_routing() -> None:
    resolver = QuoteResolver(make_quote(GasolineGrade.REGULAR))
    service, routes, _ = make_service(
        grade=GasolineGrade.PREMIUM,
        automatic_resolver=resolver,
    )

    with pytest.raises(ValueError, match="grade"):
        service.evaluate_trip(USER_ID, make_request())

    assert routes.calls == 0


def test_bev_never_uses_automatic_gasoline_resolver() -> None:
    resolver = QuoteResolver(make_quote())
    service, routes, _ = make_service(
        electric=True,
        automatic_resolver=resolver,
    )

    result = service.evaluate_trip(
        USER_ID,
        make_request(),
        price_per_kilowatt_hour=Decimal("0.25"),
    )

    assert result.evaluation.trip.decision.eligible_count == 2
    assert routes.calls == 1
    assert resolver.calls == []


def test_bev_without_electricity_price_is_rejected() -> None:
    resolver = QuoteResolver(make_quote())
    service, routes, _ = make_service(
        electric=True,
        automatic_resolver=resolver,
    )

    with pytest.raises(EnergyInputMismatchError):
        service.evaluate_trip(USER_ID, make_request())

    assert routes.calls == 0
    assert resolver.calls == []


def test_unavailable_automatic_price_stops_before_routing() -> None:
    from routevalue.application.gasoline_price_failures import (
        GasolinePriceUnavailableError,
        GasolinePriceUnavailableReason,
    )

    calls: list[GasolineGrade] = []

    def unavailable(
        origin: ResolvedLocation,
        grade: GasolineGrade,
    ) -> GasolinePriceQuote:
        calls.append(grade)
        raise GasolinePriceUnavailableError(GasolinePriceUnavailableReason.PRICE_STALE)

    service, routes, _ = make_service(
        automatic_resolver=unavailable,
    )

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        service.evaluate_trip(USER_ID, make_request())

    assert exc.value.reason is GasolinePriceUnavailableReason.PRICE_STALE
    assert calls == [GasolineGrade.REGULAR]
    assert routes.calls == 0


def test_explicit_vehicle_id_preserves_owned_profile_lookup() -> None:
    resolver = QuoteResolver(make_quote())
    service, _, profile = make_service(
        automatic_resolver=resolver,
    )

    service.evaluate_trip(
        USER_ID,
        make_request(),
        requested_vehicle_id=VEHICLE_ID,
    )

    profile.resolve_profile.assert_called_once_with(
        USER_ID,
        requested_vehicle_id=VEHICLE_ID,
    )
