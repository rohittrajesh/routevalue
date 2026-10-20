"""Monitor original source freshness without downloading or changing prices."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import OperationalError

from routevalue.domain.models import GasolineGrade
from routevalue.infrastructure.pricing import eia_health_check as health
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_quote_normalization import normalize_eia_observations
from routevalue.infrastructure.pricing.eia_snapshot_cache import EiaPricingSnapshot
from routevalue.infrastructure.pricing.eia_xls_models import EiaGasolineObservation


def snapshot(region: EiaGasolineRegion) -> EiaPricingSnapshot:
    return EiaPricingSnapshot(
        region=region,
        quotes=normalize_eia_observations(
            observations=tuple(
                EiaGasolineObservation(
                    series_id=region.series_for_grade(grade),
                    fuel_grade=grade,
                    observed_on=date(2026, 10, 12),
                    price_per_gallon=Decimal("4.125"),
                )
                for grade in GasolineGrade
            ),
            region=region,
        ),
        refreshed_at=datetime(2026, 10, 14, tzinfo=UTC),
    )


class Reader:
    def __init__(
        self, *, missing: bool = False, failure: bool = False, future: bool = False
    ) -> None:
        self.missing = missing
        self.failure = failure
        self.future = future

    def get_snapshot(self, region: EiaGasolineRegion) -> EiaPricingSnapshot | None:
        if self.failure:
            raise OperationalError("secret-url-sql", {}, Exception("secret-password"))
        if self.missing and region == EIA_CALIFORNIA_REGION:
            return None
        value = snapshot(region)
        return (
            replace(value, refreshed_at=datetime(2026, 11, 1, tzinfo=UTC)) if self.future else value
        )


@pytest.mark.parametrize(
    "checked,healthy",
    [
        (datetime(2026, 10, 19, 23, tzinfo=UTC), True),
        (datetime(2026, 10, 20, 15, 59, tzinfo=UTC), True),
        (datetime(2026, 10, 20, 16, tzinfo=UTC), False),
    ],
)
def test_health_matches_resolver_release_deadline(checked: datetime, healthy: bool) -> None:
    result = health.pricing_health(Reader(), as_of=checked)
    assert result["healthy"] is healthy
    rendered = json.dumps(result)
    assert "2026-10-12T00:00:00+00:00" in rendered
    assert "4.125" not in rendered
    assert ('unusable_grades": []' in rendered) is healthy


def test_missing_region_is_not_hidden_by_national_fallback() -> None:
    report = health.pricing_health(Reader(missing=True), as_of=datetime(2026, 10, 19, tzinfo=UTC))
    assert report["healthy"] is False
    assert "missing" in json.dumps(report)
    assert EIA_US_REGION.geography.region_id in json.dumps(report)


def test_future_refresh_cannot_make_monitor_healthy() -> None:
    report = health.pricing_health(Reader(future=True), as_of=datetime(2026, 10, 19, tzinfo=UTC))
    assert report["healthy"] is False
    assert '"future_refresh": true' in json.dumps(report)


def test_storage_failure_is_safe_and_unhealthy() -> None:
    report = health.pricing_health(Reader(failure=True), as_of=datetime(2026, 10, 19, tzinfo=UTC))
    rendered = json.dumps(report)
    assert report["healthy"] is False
    assert "unavailable" in rendered
    assert "secret" not in rendered


def test_cli_configuration_failure_has_nonzero_exit_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "invalid-secret-password")
    assert health.main() == 2
    assert "secret" not in capsys.readouterr().out


def test_naive_monitor_clock_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        health.pricing_health(
            Reader(), as_of=datetime(2026, 10, 19, tzinfo=UTC).replace(tzinfo=None)
        )
