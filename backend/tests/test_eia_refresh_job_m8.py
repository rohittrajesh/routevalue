"""Tests for the explicit EIA refresh job entry point.

No real HTTP requests or PostgreSQL connections are performed.
"""

import logging
from datetime import UTC, datetime
from typing import cast

import httpx
import pytest
from sqlalchemy.engine import Engine

from routevalue.infrastructure.pricing import (
    eia_refresh_job as job_module,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_refresh_models import (
    EiaRefreshFailureReason,
    EiaRefreshResult,
    EiaRefreshStatus,
)

REFRESHED_AT = datetime(2026, 10, 13, 18, tzinfo=UTC)


def test_missing_execute_flag_prevents_all_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_database_access() -> str:
        raise AssertionError("Database accessed without --execute")

    monkeypatch.setattr(
        job_module,
        "_validated_local_url",
        forbidden_database_access,
    )

    assert job_module.main([]) == 2


def test_missing_database_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)

    with pytest.raises(
        ValueError,
        match="not configured",
    ):
        job_module._validated_local_url()


def test_nonlocal_database_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL_UNPOOLED",
        "postgresql+psycopg://example:secret@db.example.com:5432/production",
    )

    with pytest.raises(
        ValueError,
        match="isolated local M8 database",
    ):
        job_module._validated_local_url()


@pytest.mark.parametrize(
    "region",
    [
        EIA_CALIFORNIA_REGION,
        EIA_US_REGION,
    ],
)
def test_successful_refresh_job_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
    region: EiaGasolineRegion,
) -> None:
    result = EiaRefreshResult(
        region=region,
        status=EiaRefreshStatus.SUCCEEDED,
        refreshed_at=REFRESHED_AT,
    )

    class FakeRunner:
        def __init__(self, *, coordinator: object) -> None:
            self.coordinator = coordinator

        def refresh(
            self,
            requested_region: EiaGasolineRegion,
        ) -> EiaRefreshResult:
            assert requested_region == region
            return result

    monkeypatch.setattr(
        job_module,
        "PostgresEiaPricingSnapshotRepository",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        job_module,
        "EiaWorkbookFetcher",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        job_module,
        "EiaRefreshCoordinator",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        job_module,
        "EiaSingleFlightRefreshRunner",
        FakeRunner,
    )
    monkeypatch.setattr(
        job_module,
        "EiaObservedRefreshRunner",
        FakeRunner,
    )

    status = job_module.run_refreshes(
        engine=cast(Engine, object()),
        client=cast(httpx.Client, object()),
        regions=(region,),
    )

    assert status == 0


def test_failed_region_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    class FakeRunner:
        def __init__(self, *, coordinator: object) -> None:
            self.coordinator = coordinator

        def refresh(
            self,
            region: EiaGasolineRegion,
        ) -> EiaRefreshResult:
            called.append(region.geography.region_id)

            if region == EIA_CALIFORNIA_REGION:
                return EiaRefreshResult(
                    region=region,
                    status=EiaRefreshStatus.FAILED,
                    failure_reason=(EiaRefreshFailureReason.DOWNLOAD_FAILED),
                )

            return EiaRefreshResult(
                region=region,
                status=EiaRefreshStatus.SUCCEEDED,
                refreshed_at=REFRESHED_AT,
            )

    for name in (
        "PostgresEiaPricingSnapshotRepository",
        "EiaWorkbookFetcher",
        "EiaRefreshCoordinator",
    ):
        monkeypatch.setattr(
            job_module,
            name,
            lambda **kwargs: object(),
        )

    monkeypatch.setattr(
        job_module,
        "EiaSingleFlightRefreshRunner",
        FakeRunner,
    )
    monkeypatch.setattr(
        job_module,
        "EiaObservedRefreshRunner",
        FakeRunner,
    )

    status = job_module.run_refreshes(
        engine=cast(Engine, object()),
        client=cast(httpx.Client, object()),
        regions=(EIA_CALIFORNIA_REGION, EIA_US_REGION),
    )

    assert status == 1
    assert called == ["SCA", "NUS"]


def test_setup_failure_does_not_leak_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "secret-database-password"

    def failing_configuration() -> str:
        raise RuntimeError(secret)

    monkeypatch.setattr(
        job_module,
        "_validated_local_url",
        failing_configuration,
    )

    with caplog.at_level(logging.ERROR):
        result = job_module.main(["--execute"])

    assert result == 1
    assert "exception_type=RuntimeError" in caplog.text
    assert secret not in caplog.text
