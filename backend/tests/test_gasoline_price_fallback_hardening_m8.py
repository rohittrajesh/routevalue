"""M8 fallback failure-isolation and lookup-budget tests."""

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
    MAX_GEOGRAPHIC_LOOKUPS,
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


def make_geography(
    scope: GasolinePriceGeographicScope,
    name: str,
) -> GasolinePriceGeography:
    return GasolinePriceGeography(
        scope=scope,
        region_id=name,
        display_name=name,
    )


METRO = make_geography(
    GasolinePriceGeographicScope.METRO,
    "test-metro",
)
REGION = make_geography(
    GasolinePriceGeographicScope.REGION,
    "test-region",
)
NATIONAL = make_geography(
    GasolinePriceGeographicScope.NATIONAL,
    "test-national",
)


def make_quote(
    geography: GasolinePriceGeography,
    *,
    grade: GasolineGrade = GasolineGrade.PREMIUM,
    age_days: int = 1,
) -> GasolinePriceQuote:
    return GasolinePriceQuote(
        price_per_gallon=Decimal("4.759"),
        fuel_grade=grade,
        source=GasolinePriceSource.REGIONAL_MARKET,
        observed_at=AS_OF - timedelta(days=age_days),
        market_metadata=GasolineMarketMetadata(
            provider="EIA",
            geography=geography,
        ),
    )


class FakeProvider:
    def __init__(
        self,
        responses: dict[
            str,
            GasolinePriceQuote | GasolinePriceUnavailableError | GasolinePriceProviderError | None,
        ],
    ) -> None:
        self.responses = responses
        self.requests: list[GasolinePriceLookupRequest] = []

    def get_price(
        self,
        request: GasolinePriceLookupRequest,
    ) -> GasolinePriceQuote | None:
        self.requests.append(request)

        response = self.responses.get(request.geography.region_id)

        if isinstance(response, Exception):
            raise response

        return response


def resolve(
    provider: FakeProvider,
    plan: GasolinePriceFallbackPlan | None = None,
    *,
    override: GasolinePriceQuote | None = None,
) -> GasolinePriceQuote:
    return resolve_geographic_gasoline_price(
        provider=provider,
        fuel_grade=GasolineGrade.PREMIUM,
        plan=plan
        or GasolinePriceFallbackPlan(
            geographies=(METRO, REGION, NATIONAL),
        ),
        as_of=AS_OF,
        user_override=override,
    )


def unavailable(
    reason: GasolinePriceUnavailableReason,
) -> GasolinePriceUnavailableError:
    return GasolinePriceUnavailableError(reason)


def test_unsupported_metro_falls_back_to_region() -> None:
    regional_quote = make_quote(REGION)

    provider = FakeProvider(
        {
            METRO.region_id: unavailable(GasolinePriceUnavailableReason.UNSUPPORTED_GEOGRAPHY),
            REGION.region_id: regional_quote,
        }
    )

    assert resolve(provider) is regional_quote
    assert len(provider.requests) == 2


def test_unsupported_grade_in_metro_falls_back() -> None:
    regional_quote = make_quote(REGION)

    provider = FakeProvider(
        {
            METRO.region_id: unavailable(GasolinePriceUnavailableReason.UNSUPPORTED_GRADE),
            REGION.region_id: regional_quote,
        }
    )

    assert resolve(provider) is regional_quote
    assert len(provider.requests) == 2


@pytest.mark.parametrize(
    "reason",
    [
        GasolinePriceUnavailableReason.UNSUPPORTED_GEOGRAPHY,
        GasolinePriceUnavailableReason.UNSUPPORTED_GRADE,
    ],
)
def test_exhausted_unsupported_market_preserves_reason(
    reason: GasolinePriceUnavailableReason,
) -> None:
    provider = FakeProvider(
        {
            METRO.region_id: unavailable(reason),
            REGION.region_id: unavailable(reason),
            NATIONAL.region_id: unavailable(reason),
        }
    )

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve(provider)

    assert exc.value.reason is reason
    assert len(provider.requests) == 3


@pytest.mark.parametrize(
    "reason",
    list(GasolinePriceProviderFailureReason),
)
def test_operational_failures_stop_immediately(
    reason: GasolinePriceProviderFailureReason,
) -> None:
    provider = FakeProvider(
        {
            METRO.region_id: GasolinePriceProviderError(reason),
            REGION.region_id: make_quote(REGION),
        }
    )

    with pytest.raises(GasolinePriceProviderError) as exc:
        resolve(provider)

    assert exc.value.reason is reason
    assert len(provider.requests) == 1


def test_wrong_grade_quote_does_not_fallback() -> None:
    provider = FakeProvider(
        {
            METRO.region_id: make_quote(
                METRO,
                grade=GasolineGrade.REGULAR,
            ),
            REGION.region_id: make_quote(REGION),
        }
    )

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve(provider)

    assert exc.value.reason is GasolinePriceUnavailableReason.GRADE_MISMATCH
    assert len(provider.requests) == 1


def test_wrong_geography_quote_does_not_fallback() -> None:
    provider = FakeProvider(
        {
            METRO.region_id: make_quote(REGION),
            REGION.region_id: make_quote(REGION),
        }
    )

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve(provider)

    assert exc.value.reason is GasolinePriceUnavailableReason.GEOGRAPHY_MISMATCH
    assert len(provider.requests) == 1


def test_invalid_quote_reason_from_provider_stops() -> None:
    provider = FakeProvider(
        {
            METRO.region_id: unavailable(GasolinePriceUnavailableReason.INVALID_QUOTE),
            REGION.region_id: make_quote(REGION),
        }
    )

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve(provider)

    assert exc.value.reason is GasolinePriceUnavailableReason.INVALID_QUOTE
    assert len(provider.requests) == 1


def test_stale_then_unsupported_preserves_stale_reason() -> None:
    provider = FakeProvider(
        {
            METRO.region_id: make_quote(METRO, age_days=8),
            REGION.region_id: unavailable(GasolinePriceUnavailableReason.UNSUPPORTED_GRADE),
        }
    )

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve(provider)

    assert exc.value.reason is GasolinePriceUnavailableReason.PRICE_STALE
    assert len(provider.requests) == 3


def test_manual_override_bypasses_failing_provider() -> None:
    override = GasolinePriceQuote(
        price_per_gallon=Decimal("5.19"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    provider = FakeProvider(
        {
            METRO.region_id: GasolinePriceProviderError(GasolinePriceProviderFailureReason.TIMEOUT),
        }
    )

    assert resolve(provider, override=override) is override
    assert provider.requests == []


def test_maximum_lookup_count_is_bounded() -> None:
    station = make_geography(
        GasolinePriceGeographicScope.STATION,
        "station",
    )
    state = make_geography(
        GasolinePriceGeographicScope.STATE,
        "state",
    )

    plan = GasolinePriceFallbackPlan(
        geographies=(
            station,
            METRO,
            state,
            REGION,
            NATIONAL,
        )
    )

    provider = FakeProvider({})

    with pytest.raises(GasolinePriceUnavailableError):
        resolve(provider, plan)

    assert MAX_GEOGRAPHIC_LOOKUPS == 5
    assert len(provider.requests) == MAX_GEOGRAPHIC_LOOKUPS


def test_excessive_lookup_plan_is_rejected() -> None:
    geographies = tuple(
        make_geography(
            GasolinePriceGeographicScope.REGION,
            f"region-{index}",
        )
        for index in range(MAX_GEOGRAPHIC_LOOKUPS + 1)
    )

    with pytest.raises(ValueError, match="too many geographic lookups"):
        GasolinePriceFallbackPlan(geographies=geographies)


def test_mixed_missing_and_unsupported_is_deterministic() -> None:
    provider = FakeProvider(
        {
            METRO.region_id: None,
            REGION.region_id: unavailable(GasolinePriceUnavailableReason.UNSUPPORTED_GEOGRAPHY),
            NATIONAL.region_id: unavailable(GasolinePriceUnavailableReason.UNSUPPORTED_GRADE),
        }
    )

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve(provider)

    assert exc.value.reason is GasolinePriceUnavailableReason.UNSUPPORTED_GRADE
    assert len(provider.requests) == 3
