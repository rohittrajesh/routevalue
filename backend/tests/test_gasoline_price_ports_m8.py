"""M8 provider-neutral gasoline pricing port tests."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from routevalue.application.gasoline_price_ports import (
    GasolinePriceLookupRequest,
    GasolinePriceProvider,
)
from routevalue.domain.gasoline_price_metadata import (
    GasolineMarketMetadata,
    GasolinePriceGeographicScope,
    GasolinePriceGeography,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
)


def make_geography() -> GasolinePriceGeography:
    return GasolinePriceGeography(
        scope=GasolinePriceGeographicScope.REGION,
        region_id="test-region",
        display_name="Test Region",
    )


def make_request() -> GasolinePriceLookupRequest:
    return GasolinePriceLookupRequest(
        fuel_grade=GasolineGrade.PREMIUM,
        geography=make_geography(),
    )


class FakeGasolinePriceProvider:
    """Deterministic provider used without any network calls."""

    def __init__(
        self,
        quote: GasolinePriceQuote | None,
    ) -> None:
        self.quote = quote
        self.requests: list[GasolinePriceLookupRequest] = []

    def get_price(
        self,
        request: GasolinePriceLookupRequest,
    ) -> GasolinePriceQuote | None:
        self.requests.append(request)
        return self.quote


def test_lookup_request_preserves_grade_and_geography() -> None:
    geography = make_geography()

    request = GasolinePriceLookupRequest(
        fuel_grade=GasolineGrade.PREMIUM,
        geography=geography,
    )

    assert request.fuel_grade is GasolineGrade.PREMIUM
    assert request.geography is geography


def test_lookup_request_rejects_invalid_grade() -> None:
    with pytest.raises(TypeError, match="GasolineGrade"):
        GasolinePriceLookupRequest(
            fuel_grade="premium",  # type: ignore[arg-type]
            geography=make_geography(),
        )


def test_lookup_request_rejects_invalid_geography() -> None:
    with pytest.raises(TypeError, match="GasolinePriceGeography"):
        GasolinePriceLookupRequest(
            fuel_grade=GasolineGrade.REGULAR,
            geography="test-region",  # type: ignore[arg-type]
        )


def test_lookup_request_is_immutable() -> None:
    request = make_request()

    with pytest.raises(FrozenInstanceError):
        request.fuel_grade = GasolineGrade.REGULAR  # type: ignore[misc]


def test_provider_returns_normalized_market_quote() -> None:
    geography = make_geography()

    quote = GasolinePriceQuote(
        price_per_gallon=Decimal("4.759"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=GasolinePriceSource.REGIONAL_MARKET,
        observed_at=datetime(2026, 10, 12, tzinfo=UTC),
        market_metadata=GasolineMarketMetadata(
            provider="EIA",
            geography=geography,
        ),
    )

    provider: GasolinePriceProvider = FakeGasolinePriceProvider(quote)

    result = provider.get_price(
        GasolinePriceLookupRequest(
            fuel_grade=GasolineGrade.PREMIUM,
            geography=geography,
        )
    )

    assert result is quote
    assert result is not None
    assert result.fuel_grade is GasolineGrade.PREMIUM
    assert result.market_metadata is not None
    assert result.market_metadata.geography == geography


def test_provider_can_report_missing_price() -> None:
    provider: GasolinePriceProvider = FakeGasolinePriceProvider(None)

    result = provider.get_price(make_request())

    assert result is None


def test_provider_receives_exact_lookup_request() -> None:
    fake = FakeGasolinePriceProvider(None)

    request = make_request()

    fake.get_price(request)

    assert fake.requests == [request]
    assert fake.requests[0] is request


def test_provider_exception_is_not_silently_swallowed() -> None:
    class FailingProvider:
        def get_price(
            self,
            request: GasolinePriceLookupRequest,
        ) -> GasolinePriceQuote | None:
            raise RuntimeError("simulated provider failure")

    provider: GasolinePriceProvider = FailingProvider()

    with pytest.raises(RuntimeError, match="simulated provider failure"):
        provider.get_price(make_request())
