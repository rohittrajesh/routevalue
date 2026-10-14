"""M8 deterministic geographic gasoline price fallback tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from routevalue.application.gasoline_price_failures import (
    GasolinePriceProviderError,
    GasolinePriceProviderFailureReason,
    GasolinePriceUnavailableError,
    GasolinePriceUnavailableReason,
)
from routevalue.application.gasoline_price_fallback import (
    GasolinePriceFallbackPlan,
    resolve_geographic_gasoline_price,
)
from routevalue.application.gasoline_price_ports import (
    GasolinePriceLookupRequest,
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

AS_OF = datetime(2026, 10, 13, 12, tzinfo=UTC)


def geography(
    scope: GasolinePriceGeographicScope,
    region_id: str,
) -> GasolinePriceGeography:
    return GasolinePriceGeography(
        scope=scope,
        region_id=region_id,
        display_name=region_id,
    )


METRO = geography(
    GasolinePriceGeographicScope.METRO,
    "example-metro",
)
REGION = geography(
    GasolinePriceGeographicScope.REGION,
    "example-region",
)
NATIONAL = geography(
    GasolinePriceGeographicScope.NATIONAL,
    "us",
)


def make_plan() -> GasolinePriceFallbackPlan:
    return GasolinePriceFallbackPlan(
        geographies=(METRO, REGION, NATIONAL),
    )


def make_quote(
    location: GasolinePriceGeography,
    *,
    age_days: int = 1,
    grade: GasolineGrade = GasolineGrade.PREMIUM,
) -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal("4.759"),
        fuel_grade=grade,
        source=GasolinePriceSource.REGIONAL_MARKET,
        observed_at=AS_OF - timedelta(days=age_days),
        market_metadata=GasolineMarketMetadata(
            provider="EIA",
            geography=location,
        ),
    )


class FakeProvider:
    def __init__(
        self,
        quotes: dict[str, GasolinePriceQuote | None],
    ) -> None:
        self.quotes = quotes
        self.requests: list[GasolinePriceLookupRequest] = []

    def get_price(
        self,
        request: GasolinePriceLookupRequest,
    ) -> GasolinePriceQuote | None:
        self.requests.append(request)
        return self.quotes.get(request.geography.region_id)


def resolve(
    provider: FakeProvider,
    *,
    override: GasolinePriceQuote | None = None,
) -> GasolinePriceQuote:
    return resolve_geographic_gasoline_price(
        provider=provider,
        fuel_grade=GasolineGrade.PREMIUM,
        plan=make_plan(),
        as_of=AS_OF,
        user_override=override,
    )


def test_first_matching_market_wins() -> None:
    metro_quote = make_quote(METRO)
    provider = FakeProvider(
        {
            METRO.region_id: metro_quote,
            REGION.region_id: make_quote(REGION),
        }
    )

    assert resolve(provider) is metro_quote
    assert len(provider.requests) == 1


def test_missing_metro_falls_back_to_region() -> None:
    regional_quote = make_quote(REGION)
    provider = FakeProvider(
        {
            REGION.region_id: regional_quote,
        }
    )

    assert resolve(provider) is regional_quote
    assert [request.geography for request in provider.requests] == [METRO, REGION]


def test_missing_region_falls_back_to_national() -> None:
    national_quote = make_quote(NATIONAL)
    provider = FakeProvider(
        {
            NATIONAL.region_id: national_quote,
        }
    )

    assert resolve(provider) is national_quote
    assert len(provider.requests) == 3


def test_stale_regional_price_uses_national_fallback() -> None:
    national_quote = make_quote(NATIONAL)

    provider = FakeProvider(
        {
            METRO.region_id: make_quote(METRO, age_days=8),
            REGION.region_id: None,
            NATIONAL.region_id: national_quote,
        }
    )

    assert resolve(provider) is national_quote


def test_manual_override_bypasses_provider() -> None:
    override = GasolinePriceQuote(
        price_per_gallon=Decimal("5.15"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )
    provider = FakeProvider({})

    assert resolve(provider, override=override) is override
    assert provider.requests == []


def test_wrong_grade_does_not_trigger_broader_fallback() -> None:
    provider = FakeProvider(
        {
            METRO.region_id: make_quote(
                METRO,
                grade=GasolineGrade.REGULAR,
            ),
            REGION.region_id: make_quote(REGION),
        }
    )

    with pytest.raises(GasolinePriceUnavailableError) as error:
        resolve(provider)

    assert error.value.reason is GasolinePriceUnavailableReason.GRADE_MISMATCH
    assert len(provider.requests) == 1


def test_missing_prices_are_explicit() -> None:
    provider = FakeProvider({})

    with pytest.raises(GasolinePriceUnavailableError) as error:
        resolve(provider)

    assert error.value.reason is GasolinePriceUnavailableReason.PRICE_NOT_FOUND
    assert len(provider.requests) == 3


def test_all_stale_prices_are_explicit() -> None:
    provider = FakeProvider(
        {
            METRO.region_id: make_quote(METRO, age_days=8),
            REGION.region_id: make_quote(REGION, age_days=8),
            NATIONAL.region_id: make_quote(NATIONAL, age_days=8),
        }
    )

    with pytest.raises(GasolinePriceUnavailableError) as error:
        resolve(provider)

    assert error.value.reason is GasolinePriceUnavailableReason.PRICE_STALE


def test_fallback_plan_rejects_duplicate_geography() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        GasolinePriceFallbackPlan(
            geographies=(METRO, METRO),
        )


def test_fallback_plan_rejects_reversed_order() -> None:
    with pytest.raises(ValueError, match="specific to broad"):
        GasolinePriceFallbackPlan(
            geographies=(NATIONAL, METRO),
        )


def test_fallback_plan_rejects_empty_plan() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        GasolinePriceFallbackPlan(geographies=())


def test_provider_failure_is_not_silently_ignored() -> None:
    class FailingProvider:
        def get_price(
            self,
            request: GasolinePriceLookupRequest,
        ) -> GasolinePriceQuote | None:
            raise GasolinePriceProviderError(GasolinePriceProviderFailureReason.TIMEOUT)

    with pytest.raises(GasolinePriceProviderError) as error:
        resolve_geographic_gasoline_price(
            provider=FailingProvider(),
            fuel_grade=GasolineGrade.PREMIUM,
            plan=make_plan(),
            as_of=AS_OF,
        )

    assert error.value.reason is GasolinePriceProviderFailureReason.TIMEOUT


def test_deterministic_fallback_selection() -> None:
    quote = make_quote(REGION)

    provider = FakeProvider(
        {
            REGION.region_id: quote,
        }
    )

    first = resolve(provider)
    second = resolve(provider)

    assert first is quote
    assert second is quote
    assert len(provider.requests) == 4
