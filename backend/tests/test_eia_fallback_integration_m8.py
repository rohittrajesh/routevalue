"""M8 integration tests for EIA gasoline geographic fallback."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from routevalue.application.gasoline_price_fallback import (
    GasolinePriceFallbackPlan,
    resolve_geographic_gasoline_price,
)
from routevalue.application.gasoline_price_ports import (
    GasolinePriceLookupRequest,
)
from routevalue.domain.gasoline_price_metadata import (
    GasolinePriceGeography,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaPricingReference,
    build_eia_fallback_plan,
)
from routevalue.infrastructure.pricing.eia_quote_normalization import (
    normalize_eia_observation,
)
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaGasolineObservation,
)

FRESH_AS_OF = datetime(2026, 10, 12, tzinfo=UTC)
STALE_AS_OF = datetime(2026, 10, 13, tzinfo=UTC)


def make_eia_quote(
    *,
    region_id: str,
    grade: GasolineGrade = GasolineGrade.PREMIUM,
    price: str = "6.677",
    observed_on: date = date(2026, 10, 5),
) -> GasolinePriceQuote:
    region = EIA_CALIFORNIA_REGION if region_id == "SCA" else EIA_US_REGION

    observation = EiaGasolineObservation(
        series_id=region.series_for_grade(grade),
        fuel_grade=grade,
        observed_on=observed_on,
        price_per_gallon=Decimal(price),
    )

    return normalize_eia_observation(
        observation=observation,
        region=region,
    )


class FakeEiaProvider:
    """Return pre-normalized quotes without external requests."""

    def __init__(
        self,
        quotes: dict[
            GasolinePriceGeography,
            GasolinePriceQuote | None,
        ],
    ) -> None:
        self.quotes = quotes
        self.calls: list[GasolinePriceLookupRequest] = []

    def get_price(
        self,
        request: GasolinePriceLookupRequest,
    ) -> GasolinePriceQuote | None:
        self.calls.append(request)
        return self.quotes.get(request.geography)


def make_california_plan() -> GasolinePriceFallbackPlan:
    """Build the verified California-to-national fallback plan."""
    return build_eia_fallback_plan(EiaPricingReference.CALIFORNIA)


def test_california_quote_wins_when_fresh() -> None:
    california = make_eia_quote(region_id="SCA")
    national = make_eia_quote(
        region_id="NUS",
        price="5.400",
    )

    provider = FakeEiaProvider(
        {
            EIA_CALIFORNIA_REGION.geography: california,
            EIA_US_REGION.geography: national,
        }
    )

    selected = resolve_geographic_gasoline_price(
        provider=provider,
        fuel_grade=GasolineGrade.PREMIUM,
        plan=make_california_plan(),
        as_of=FRESH_AS_OF,
    )

    assert selected == california
    assert len(provider.calls) == 1
    assert provider.calls[0].geography == EIA_CALIFORNIA_REGION.geography


def test_missing_california_price_uses_national_fallback() -> None:
    national = make_eia_quote(
        region_id="NUS",
        price="5.400",
    )

    provider = FakeEiaProvider(
        {
            EIA_US_REGION.geography: national,
        }
    )

    selected = resolve_geographic_gasoline_price(
        provider=provider,
        fuel_grade=GasolineGrade.PREMIUM,
        plan=make_california_plan(),
        as_of=FRESH_AS_OF,
    )

    assert selected == national
    assert [call.geography for call in provider.calls] == [
        EIA_CALIFORNIA_REGION.geography,
        EIA_US_REGION.geography,
    ]


def test_stale_california_price_uses_fresh_national() -> None:
    california = make_eia_quote(
        region_id="SCA",
        observed_on=date(2026, 10, 1),
    )
    national = make_eia_quote(
        region_id="NUS",
        price="5.400",
    )

    provider = FakeEiaProvider(
        {
            EIA_CALIFORNIA_REGION.geography: california,
            EIA_US_REGION.geography: national,
        }
    )

    selected = resolve_geographic_gasoline_price(
        provider=provider,
        fuel_grade=GasolineGrade.PREMIUM,
        plan=make_california_plan(),
        as_of=FRESH_AS_OF,
    )

    assert selected == national
    assert len(provider.calls) == 2


def test_manual_override_bypasses_provider() -> None:
    manual = GasolinePriceQuote(
        price_per_gallon=Decimal("4.999"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    provider = FakeEiaProvider({})

    selected = resolve_geographic_gasoline_price(
        provider=provider,
        fuel_grade=GasolineGrade.PREMIUM,
        plan=make_california_plan(),
        as_of=STALE_AS_OF,
        user_override=manual,
    )

    assert selected == manual
    assert provider.calls == []


def test_national_reference_only_requests_national() -> None:
    national = make_eia_quote(
        region_id="NUS",
        price="5.400",
    )
    provider = FakeEiaProvider({EIA_US_REGION.geography: national})

    selected = resolve_geographic_gasoline_price(
        provider=provider,
        fuel_grade=GasolineGrade.PREMIUM,
        plan=build_eia_fallback_plan(EiaPricingReference.UNITED_STATES),
        as_of=FRESH_AS_OF,
    )

    assert selected == national
    assert len(provider.calls) == 1
    assert provider.calls[0].geography == EIA_US_REGION.geography


def test_provider_receives_requested_grade() -> None:
    regular = make_eia_quote(
        region_id="SCA",
        grade=GasolineGrade.REGULAR,
        price="6.227",
    )
    provider = FakeEiaProvider({EIA_CALIFORNIA_REGION.geography: regular})

    selected = resolve_geographic_gasoline_price(
        provider=provider,
        fuel_grade=GasolineGrade.REGULAR,
        plan=make_california_plan(),
        as_of=FRESH_AS_OF,
    )

    assert selected == regular
    assert provider.calls[0].fuel_grade is GasolineGrade.REGULAR


def test_operational_failure_is_not_silently_ignored() -> None:
    class BrokenProvider:
        def get_price(
            self,
            request: GasolinePriceLookupRequest,
        ) -> GasolinePriceQuote | None:
            raise RuntimeError("simulated provider failure")

    with pytest.raises(RuntimeError, match="simulated provider failure"):
        resolve_geographic_gasoline_price(
            provider=BrokenProvider(),
            fuel_grade=GasolineGrade.PREMIUM,
            plan=make_california_plan(),
            as_of=FRESH_AS_OF,
        )
