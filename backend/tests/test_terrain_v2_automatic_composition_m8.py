"""M8-R2 tests for safe automatic gasoline pricing dependency composition."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import Mock

import pytest

from routevalue.api.terrain_v2_composition import build_terrain_v2_evaluation_service
from routevalue.api.terrain_v2_service import TerrainV2EvaluationService
from routevalue.application.gasoline_price_geography import (
    PricingJurisdiction,
    PricingJurisdictionResolver,
    PricingJurisdictionResult,
)
from routevalue.application.gasoline_price_ports import (
    GasolinePriceLookupRequest,
    GasolinePriceProvider,
)
from routevalue.application.models import ResolvedLocation
from routevalue.application.ports import (
    RouteProvider,
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.domain.gasoline_price_metadata import GasolineMarketMetadata
from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
)
from routevalue.infrastructure.pricing.eia_geography import EIA_CALIFORNIA_REGION

AS_OF = datetime(2026, 10, 14, 12, tzinfo=UTC)
OBSERVED_AT = datetime(2026, 10, 12, tzinfo=UTC)


def make_quote() -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal("6.227"),
        fuel_grade=GasolineGrade.REGULAR,
        source=GasolinePriceSource.REGIONAL_MARKET,
        observed_at=OBSERVED_AT,
        market_metadata=GasolineMarketMetadata(
            provider="EIA",
            geography=EIA_CALIFORNIA_REGION.geography,
        ),
    )


def make_dependencies() -> tuple[Mock, Mock, Mock]:
    return (
        Mock(spec=UserPreferencesRepository),
        Mock(spec=SavedVehicleRepository),
        Mock(spec=RouteProvider),
    )


def build(
    *,
    provider: GasolinePriceProvider | None = None,
    jurisdiction_resolver: PricingJurisdictionResolver | None = None,
    pricing_clock: Callable[[], datetime] | None = None,
) -> TerrainV2EvaluationService:
    preferences, vehicles, routes = make_dependencies()
    return build_terrain_v2_evaluation_service(
        preferences_repository=cast(UserPreferencesRepository, preferences),
        saved_vehicle_repository=cast(SavedVehicleRepository, vehicles),
        route_provider=cast(RouteProvider, routes),
        gasoline_price_provider=provider,
        gasoline_jurisdiction_resolver=jurisdiction_resolver,
        pricing_clock=pricing_clock,
    )


def test_automatic_pricing_is_disabled_by_default() -> None:
    service = build()
    assert service.application_service.automatic_gasoline_price_resolver is None


def test_partial_pricing_configuration_is_rejected() -> None:
    provider = Mock(spec=GasolinePriceProvider)
    jurisdiction = Mock(spec=PricingJurisdictionResolver)
    with pytest.raises(ValueError, match="configured together"):
        build(provider=cast(GasolinePriceProvider, provider))
    with pytest.raises(ValueError, match="configured together"):
        build(
            jurisdiction_resolver=cast(
                PricingJurisdictionResolver,
                jurisdiction,
            )
        )


def test_clock_without_pricing_is_rejected() -> None:
    with pytest.raises(ValueError, match="pricing_clock"):
        build(pricing_clock=lambda: AS_OF)


def test_composition_does_not_call_pricing_dependencies() -> None:
    provider = Mock(spec=GasolinePriceProvider)
    jurisdiction = Mock(spec=PricingJurisdictionResolver)
    clock = Mock(return_value=AS_OF)
    service = build(
        provider=cast(GasolinePriceProvider, provider),
        jurisdiction_resolver=cast(PricingJurisdictionResolver, jurisdiction),
        pricing_clock=clock,
    )

    assert service.application_service.automatic_gasoline_price_resolver is not None
    provider.assert_not_called()
    provider.get_price.assert_not_called()
    jurisdiction.assert_not_called()
    jurisdiction.resolve.assert_not_called()
    clock.assert_not_called()


def test_resolver_uses_trusted_geography_and_clock() -> None:
    provider = Mock(spec=GasolinePriceProvider)
    jurisdiction = Mock(spec=PricingJurisdictionResolver)
    jurisdiction.resolve.return_value = PricingJurisdictionResult(
        jurisdiction=PricingJurisdiction.CALIFORNIA,
    )
    provider.get_price.return_value = make_quote()
    clock = Mock(return_value=AS_OF)
    service = build(
        provider=cast(GasolinePriceProvider, provider),
        jurisdiction_resolver=cast(PricingJurisdictionResolver, jurisdiction),
        pricing_clock=clock,
    )

    automatic_resolver = service.application_service.automatic_gasoline_price_resolver
    assert automatic_resolver is not None
    origin = ResolvedLocation("Los Angeles", 34.0, -118.0)
    quote = automatic_resolver(origin, GasolineGrade.REGULAR)

    assert quote == make_quote()
    assert quote.source is GasolinePriceSource.REGIONAL_MARKET
    assert quote.observed_at == OBSERVED_AT
    jurisdiction.resolve.assert_called_once_with(origin)
    clock.assert_called_once_with()
    provider.get_price.assert_called_once_with(
        GasolinePriceLookupRequest(
            fuel_grade=GasolineGrade.REGULAR,
            geography=EIA_CALIFORNIA_REGION.geography,
        )
    )


def test_naive_clock_is_rejected_before_price_lookup() -> None:
    provider = Mock(spec=GasolinePriceProvider)
    jurisdiction = Mock(spec=PricingJurisdictionResolver)
    service = build(
        provider=cast(GasolinePriceProvider, provider),
        jurisdiction_resolver=cast(PricingJurisdictionResolver, jurisdiction),
        pricing_clock=lambda: datetime(2026, 10, 14, 12, tzinfo=None),  # noqa: DTZ001
    )

    automatic_resolver = service.application_service.automatic_gasoline_price_resolver
    assert automatic_resolver is not None

    with pytest.raises(ValueError, match="timezone-aware"):
        automatic_resolver(
            ResolvedLocation("Origin", 34.0, -118.0),
            GasolineGrade.REGULAR,
        )

    provider.get_price.assert_not_called()
    jurisdiction.resolve.assert_not_called()
