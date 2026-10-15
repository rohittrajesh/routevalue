"""M8 tests for trusted, read-only EIA trip pricing composition."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from routevalue.application.gasoline_price_failures import (
    GasolinePriceUnavailableError,
    GasolinePriceUnavailableReason,
)
from routevalue.application.gasoline_price_geography import (
    PricingGeographyUnavailableError,
    PricingJurisdiction,
    PricingJurisdictionResult,
)
from routevalue.application.gasoline_price_ports import (
    GasolinePriceLookupRequest,
)
from routevalue.application.models import ResolvedLocation
from routevalue.domain.gasoline_price_metadata import GasolineMarketMetadata
from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
)
from routevalue.infrastructure.pricing.eia_trip_price_resolution import (
    resolve_persisted_eia_gasoline_price,
)

AS_OF = datetime(2026, 10, 14, 12, tzinfo=UTC)
OBSERVED_AT = datetime(2026, 10, 12, tzinfo=UTC)

ORIGIN = ResolvedLocation(
    display_name="Test origin",
    latitude=34.0,
    longitude=-118.0,
)


class FakeJurisdictionResolver:
    def __init__(self, jurisdiction: PricingJurisdiction) -> None:
        self.jurisdiction = jurisdiction
        self.calls: list[ResolvedLocation] = []

    def resolve(
        self,
        location: ResolvedLocation,
    ) -> PricingJurisdictionResult:
        self.calls.append(location)
        return PricingJurisdictionResult(jurisdiction=self.jurisdiction)


class FakePriceProvider:
    def __init__(
        self,
        quotes: dict[str, GasolinePriceQuote] | None = None,
    ) -> None:
        self.quotes = quotes or {}
        self.requests: list[GasolinePriceLookupRequest] = []

    def get_price(
        self,
        request: GasolinePriceLookupRequest,
    ) -> GasolinePriceQuote | None:
        self.requests.append(request)
        return self.quotes.get(request.geography.region_id)


def make_quote(
    *,
    region_id: str,
    grade: GasolineGrade = GasolineGrade.REGULAR,
    observed_at: datetime = OBSERVED_AT,
) -> GasolinePriceQuote:
    region = EIA_CALIFORNIA_REGION if region_id == "SCA" else EIA_US_REGION

    return GasolinePriceQuote(
        price_per_gallon=Decimal("5.123"),
        fuel_grade=grade,
        source=GasolinePriceSource.REGIONAL_MARKET,
        observed_at=observed_at,
        market_metadata=GasolineMarketMetadata(
            provider="EIA",
            geography=region.geography,
        ),
    )


def test_california_uses_state_quote_first() -> None:
    resolver = FakeJurisdictionResolver(PricingJurisdiction.CALIFORNIA)
    provider = FakePriceProvider({"SCA": make_quote(region_id="SCA")})

    result = resolve_persisted_eia_gasoline_price(
        provider=provider,
        jurisdiction_resolver=resolver,
        origin=ORIGIN,
        fuel_grade=GasolineGrade.REGULAR,
        as_of=AS_OF,
    )

    assert result.price_per_gallon == Decimal("5.123")
    assert result.market_metadata is not None
    assert result.market_metadata.geography == EIA_CALIFORNIA_REGION.geography
    assert [r.geography.region_id for r in provider.requests] == ["SCA"]
    assert resolver.calls == [ORIGIN]


def test_california_falls_back_to_national() -> None:
    resolver = FakeJurisdictionResolver(PricingJurisdiction.CALIFORNIA)
    provider = FakePriceProvider({"NUS": make_quote(region_id="NUS")})

    result = resolve_persisted_eia_gasoline_price(
        provider=provider,
        jurisdiction_resolver=resolver,
        origin=ORIGIN,
        fuel_grade=GasolineGrade.REGULAR,
        as_of=AS_OF,
    )

    assert result.market_metadata is not None
    assert result.market_metadata.geography == EIA_US_REGION.geography
    assert [r.geography.region_id for r in provider.requests] == [
        "SCA",
        "NUS",
    ]


def test_non_california_us_uses_national_only() -> None:
    resolver = FakeJurisdictionResolver(PricingJurisdiction.OTHER_US)
    provider = FakePriceProvider(
        {
            "NUS": make_quote(
                region_id="NUS",
                grade=GasolineGrade.PREMIUM,
            )
        }
    )

    result = resolve_persisted_eia_gasoline_price(
        provider=provider,
        jurisdiction_resolver=resolver,
        origin=ORIGIN,
        fuel_grade=GasolineGrade.PREMIUM,
        as_of=AS_OF,
    )

    assert result.fuel_grade is GasolineGrade.PREMIUM
    assert [r.geography.region_id for r in provider.requests] == ["NUS"]


def test_stale_state_quote_falls_back_to_fresh_national() -> None:
    resolver = FakeJurisdictionResolver(PricingJurisdiction.CALIFORNIA)
    provider = FakePriceProvider(
        {
            "SCA": make_quote(
                region_id="SCA",
                observed_at=datetime(2026, 9, 1, tzinfo=UTC),
            ),
            "NUS": make_quote(region_id="NUS"),
        }
    )

    result = resolve_persisted_eia_gasoline_price(
        provider=provider,
        jurisdiction_resolver=resolver,
        origin=ORIGIN,
        fuel_grade=GasolineGrade.REGULAR,
        as_of=AS_OF,
    )

    assert result.market_metadata is not None
    assert result.market_metadata.geography == EIA_US_REGION.geography
    assert [r.geography.region_id for r in provider.requests] == [
        "SCA",
        "NUS",
    ]


def test_all_stale_quotes_raise_explicit_error() -> None:
    resolver = FakeJurisdictionResolver(PricingJurisdiction.CALIFORNIA)
    stale = datetime(2026, 9, 1, tzinfo=UTC)
    provider = FakePriceProvider(
        {
            "SCA": make_quote(
                region_id="SCA",
                observed_at=stale,
            ),
            "NUS": make_quote(
                region_id="NUS",
                observed_at=stale,
            ),
        }
    )

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve_persisted_eia_gasoline_price(
            provider=provider,
            jurisdiction_resolver=resolver,
            origin=ORIGIN,
            fuel_grade=GasolineGrade.REGULAR,
            as_of=AS_OF,
        )

    assert exc.value.reason is GasolinePriceUnavailableReason.PRICE_STALE


def test_missing_quotes_raise_explicit_error() -> None:
    resolver = FakeJurisdictionResolver(PricingJurisdiction.OTHER_US)
    provider = FakePriceProvider()

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve_persisted_eia_gasoline_price(
            provider=provider,
            jurisdiction_resolver=resolver,
            origin=ORIGIN,
            fuel_grade=GasolineGrade.REGULAR,
            as_of=AS_OF,
        )

    assert exc.value.reason is GasolinePriceUnavailableReason.PRICE_NOT_FOUND


@pytest.mark.parametrize(
    "jurisdiction",
    [
        PricingJurisdiction.UNKNOWN,
        PricingJurisdiction.OUTSIDE_US,
    ],
)
def test_unverified_geography_never_queries_provider(
    jurisdiction: PricingJurisdiction,
) -> None:
    resolver = FakeJurisdictionResolver(jurisdiction)
    provider = FakePriceProvider()

    with pytest.raises(PricingGeographyUnavailableError):
        resolve_persisted_eia_gasoline_price(
            provider=provider,
            jurisdiction_resolver=resolver,
            origin=ORIGIN,
            fuel_grade=GasolineGrade.REGULAR,
            as_of=AS_OF,
        )

    assert provider.requests == []
