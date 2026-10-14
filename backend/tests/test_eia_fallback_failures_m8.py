"""M8 EIA geographic fallback failure and error-semantics tests."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from routevalue.application.gasoline_price_failures import (
    GasolinePriceUnavailableError,
    GasolinePriceUnavailableReason,
)
from routevalue.application.gasoline_price_fallback import (
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

AS_OF = datetime(2026, 10, 13, tzinfo=UTC)


def make_quote(
    *,
    california: bool,
    observed_on: date = date(2026, 10, 5),
) -> GasolinePriceQuote:
    """Create a normalized regional EIA gasoline quote."""

    region = EIA_CALIFORNIA_REGION if california else EIA_US_REGION

    observation = EiaGasolineObservation(
        series_id=region.series_for_grade(GasolineGrade.PREMIUM),
        fuel_grade=GasolineGrade.PREMIUM,
        observed_on=observed_on,
        price_per_gallon=Decimal("6.677" if california else "5.400"),
    )

    return normalize_eia_observation(
        observation=observation,
        region=region,
    )


class FakeProvider:
    """Deterministic provider with no network operations."""

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


class UnsupportedGradeProvider:
    """Simulate explicit unsupported-grade responses."""

    def __init__(self) -> None:
        self.calls = 0

    def get_price(
        self,
        request: GasolinePriceLookupRequest,
    ) -> GasolinePriceQuote | None:
        self.calls += 1
        raise GasolinePriceUnavailableError(GasolinePriceUnavailableReason.UNSUPPORTED_GRADE)


class BrokenProvider:
    """Simulate an operational provider failure."""

    def __init__(self) -> None:
        self.calls = 0

    def get_price(
        self,
        request: GasolinePriceLookupRequest,
    ) -> GasolinePriceQuote | None:
        self.calls += 1
        raise RuntimeError("EIA provider operational failure")


def resolve_with_provider(
    provider: FakeProvider,
) -> GasolinePriceQuote:
    """Resolve premium gasoline using California-first fallback."""

    return resolve_geographic_gasoline_price(
        provider=provider,
        fuel_grade=GasolineGrade.PREMIUM,
        plan=build_eia_fallback_plan(EiaPricingReference.CALIFORNIA),
        as_of=AS_OF,
    )


def test_both_stale_reports_price_stale() -> None:
    provider = FakeProvider(
        {
            EIA_CALIFORNIA_REGION.geography: make_quote(california=True),
            EIA_US_REGION.geography: make_quote(california=False),
        }
    )

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve_with_provider(provider)

    assert exc.value.reason is GasolinePriceUnavailableReason.PRICE_STALE
    assert len(provider.calls) == 2


def test_both_missing_reports_price_not_found() -> None:
    provider = FakeProvider({})

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve_with_provider(provider)

    assert exc.value.reason is GasolinePriceUnavailableReason.PRICE_NOT_FOUND
    assert len(provider.calls) == 2


def test_stale_california_missing_national_reports_stale() -> None:
    provider = FakeProvider(
        {
            EIA_CALIFORNIA_REGION.geography: make_quote(california=True),
        }
    )

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve_with_provider(provider)

    assert exc.value.reason is GasolinePriceUnavailableReason.PRICE_STALE
    assert len(provider.calls) == 2


def test_unsupported_grade_reports_specific_reason() -> None:
    provider = UnsupportedGradeProvider()

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve_geographic_gasoline_price(
            provider=provider,
            fuel_grade=GasolineGrade.PREMIUM,
            plan=build_eia_fallback_plan(EiaPricingReference.CALIFORNIA),
            as_of=AS_OF,
        )

    assert exc.value.reason is GasolinePriceUnavailableReason.UNSUPPORTED_GRADE
    assert provider.calls == 2


def test_operational_failure_stops_fallback() -> None:
    provider = BrokenProvider()

    with pytest.raises(
        RuntimeError,
        match="EIA provider operational failure",
    ):
        resolve_geographic_gasoline_price(
            provider=provider,
            fuel_grade=GasolineGrade.PREMIUM,
            plan=build_eia_fallback_plan(EiaPricingReference.CALIFORNIA),
            as_of=AS_OF,
        )

    assert provider.calls == 1


def test_manual_override_bypasses_stale_data() -> None:
    manual = GasolinePriceQuote(
        price_per_gallon=Decimal("4.999"),
        fuel_grade=GasolineGrade.PREMIUM,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    provider = FakeProvider(
        {
            EIA_CALIFORNIA_REGION.geography: make_quote(california=True),
            EIA_US_REGION.geography: make_quote(california=False),
        }
    )

    selected = resolve_geographic_gasoline_price(
        provider=provider,
        fuel_grade=GasolineGrade.PREMIUM,
        plan=build_eia_fallback_plan(EiaPricingReference.CALIFORNIA),
        as_of=AS_OF,
        user_override=manual,
    )

    assert selected == manual
    assert provider.calls == []


def test_invalid_quote_does_not_trigger_silent_fallback() -> None:
    """Reject national pricing masquerading as California pricing."""

    national = make_quote(
        california=False,
        observed_on=date(2026, 10, 12),
    )

    provider = FakeProvider(
        {
            EIA_CALIFORNIA_REGION.geography: national,
            EIA_US_REGION.geography: national,
        }
    )

    with pytest.raises(GasolinePriceUnavailableError):
        resolve_with_provider(provider)

    # An invalid first quote must terminate resolution.
    assert len(provider.calls) == 1
