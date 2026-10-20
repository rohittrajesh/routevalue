"""M8 end-to-end EIA refresh integration tests.

Real components:
- EIA XLS downloader
- Workbook parser
- Observation normalizer
- Refresh coordinator
- PostgreSQL snapshot repository

External HTTP is replaced with httpx.MockTransport.
Database writes are restricted to the isolated local M8 database.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import delete, text
from sqlalchemy.engine import Engine, create_engine, make_url

from routevalue.domain.models import GasolineGrade
from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    PostgresEiaPricingSnapshotRepository,
)
from routevalue.infrastructure.persistence.schema import (
    eia_pricing_observations,
    eia_pricing_snapshots,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_quote_normalization import (
    normalize_eia_observations,
)
from routevalue.infrastructure.pricing.eia_refresh_coordinator import (
    EiaRefreshCoordinator,
)
from routevalue.infrastructure.pricing.eia_refresh_http_adapter import (
    EiaWorkbookFetcher,
)
from routevalue.infrastructure.pricing.eia_refresh_models import (
    EiaRefreshFailureReason,
    EiaRefreshStatus,
)
from routevalue.infrastructure.pricing.eia_xls_parser import (
    parse_eia_xls_workbook,
)

FIXTURES = {
    "SCA": Path("/tmp/routevalue_eia_california.xls"),
    "NUS": Path("/tmp/routevalue_eia_gasoline.xls"),
}

REFRESHED_AT = datetime(2026, 10, 13, 18, tzinfo=UTC)


@pytest.fixture
def database_engine() -> Iterator[Engine]:
    """Connect only to the dedicated local M8 PostgreSQL database."""

    raw_url = os.environ.get("DATABASE_URL_UNPOOLED")

    if not raw_url:
        pytest.skip("M8 isolated PostgreSQL URL not configured")

    url = make_url(raw_url)

    assert url.drivername == "postgresql+psycopg"
    assert url.host == "127.0.0.1"
    assert url.port == 55432
    assert url.username == "routevalue_local"
    assert url.database == "routevalue_m8_eia_test"

    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )

    def clean() -> None:
        with engine.begin() as connection:
            connection.execute(delete(eia_pricing_observations))
            connection.execute(delete(eia_pricing_snapshots))

    try:
        with engine.connect() as connection:
            identity = connection.execute(text("SELECT current_database(), current_user")).one()

            assert identity[0] == "routevalue_m8_eia_test"
            assert identity[1] == "routevalue_local"

            version = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar_one()

            assert version == "a19d6e2c740b"

        clean()
        yield engine

    finally:
        try:
            clean()
        finally:
            engine.dispose()


@pytest.fixture
def workbook_bytes() -> dict[str, bytes]:
    """Load previously downloaded real EIA workbooks locally."""

    loaded: dict[str, bytes] = {}

    for region_id, path in FIXTURES.items():
        if not path.is_file():
            pytest.fail(f"Missing EIA workbook fixture: {path}")

        content = path.read_bytes()

        assert content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"), (
            f"Invalid XLS signature: {path}"
        )

        loaded[region_id] = content

    return loaded


def make_http_client(
    workbook_bytes: dict[str, bytes],
    *,
    failing_region: str | None = None,
    malformed_region: str | None = None,
) -> httpx.Client:
    """Serve real XLS content through a network-free HTTP transport."""

    def respond(request: httpx.Request) -> httpx.Response:
        requested_url = str(request.url)

        for region in (
            EIA_CALIFORNIA_REGION,
            EIA_US_REGION,
        ):
            if requested_url != region.workbook_url:
                continue

            region_id = region.geography.region_id

            if region_id == failing_region:
                return httpx.Response(503)

            if region_id == malformed_region:
                return httpx.Response(
                    200,
                    content=b"invalid XLS workbook",
                )

            return httpx.Response(
                200,
                content=workbook_bytes[region_id],
            )

        return httpx.Response(404)

    return httpx.Client(
        transport=httpx.MockTransport(respond),
        follow_redirects=False,
    )


def make_coordinator(
    *,
    client: httpx.Client,
    engine: Engine,
    refreshed_at: datetime = REFRESHED_AT,
) -> EiaRefreshCoordinator:
    return EiaRefreshCoordinator(
        fetch_workbook=EiaWorkbookFetcher(client=client),
        repository=PostgresEiaPricingSnapshotRepository(engine=engine),
        clock=lambda: refreshed_at,
    )


def assert_roundtrip_matches_workbook(
    *,
    region: EiaGasolineRegion,
    workbook_bytes: bytes,
    engine: Engine,
    refreshed_at: datetime,
) -> None:
    """Compare persisted quotes with independently parsed source data."""

    observations = parse_eia_xls_workbook(
        workbook_bytes=workbook_bytes,
        region=region,
    )

    expected_quotes = normalize_eia_observations(
        observations=observations,
        region=region,
    )

    repository = PostgresEiaPricingSnapshotRepository(engine=engine)

    restored = repository.get_snapshot(region)

    assert restored is not None
    assert restored.region == region
    assert restored.refreshed_at == refreshed_at
    assert len(restored.quotes) == 3

    assert {quote.fuel_grade for quote in restored.quotes} == set(GasolineGrade)

    for expected in expected_quotes:
        actual = restored.quote_for_grade(expected.fuel_grade)

        assert actual.price_per_gallon == expected.price_per_gallon
        assert actual.observed_at == expected.observed_at
        assert actual.source == expected.source
        assert actual.market_metadata == expected.market_metadata


@pytest.mark.parametrize(
    "region",
    [EIA_CALIFORNIA_REGION, EIA_US_REGION],
)
def test_real_workbook_refresh_roundtrip(
    database_engine: Engine,
    workbook_bytes: dict[str, bytes],
    region: EiaGasolineRegion,
) -> None:
    """Real EIA parsing and PostgreSQL persistence succeed together."""

    with make_http_client(workbook_bytes) as client:
        coordinator = make_coordinator(
            client=client,
            engine=database_engine,
        )

        result = coordinator.refresh(region)

    assert result.status is EiaRefreshStatus.SUCCEEDED
    assert result.failure_reason is None
    assert result.refreshed_at == REFRESHED_AT

    assert_roundtrip_matches_workbook(
        region=region,
        workbook_bytes=workbook_bytes[region.geography.region_id],
        engine=database_engine,
        refreshed_at=REFRESHED_AT,
    )

    with database_engine.connect() as connection:
        observation_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM public.eia_pricing_observations WHERE region_id = :region_id"
            ),
            {"region_id": region.geography.region_id},
        ).scalar_one()

    assert observation_count == 3


def test_both_regions_can_be_persisted(
    database_engine: Engine,
    workbook_bytes: dict[str, bytes],
) -> None:
    """California and national prices coexist independently."""

    with make_http_client(workbook_bytes) as client:
        coordinator = make_coordinator(
            client=client,
            engine=database_engine,
        )

        california_result = coordinator.refresh(EIA_CALIFORNIA_REGION)
        national_result = coordinator.refresh(EIA_US_REGION)

    assert california_result.succeeded
    assert national_result.succeeded

    for region in (
        EIA_CALIFORNIA_REGION,
        EIA_US_REGION,
    ):
        assert_roundtrip_matches_workbook(
            region=region,
            workbook_bytes=workbook_bytes[region.geography.region_id],
            engine=database_engine,
            refreshed_at=REFRESHED_AT,
        )

    with database_engine.connect() as connection:
        snapshot_count = connection.execute(
            text("SELECT COUNT(*) FROM public.eia_pricing_snapshots")
        ).scalar_one()

        observation_count = connection.execute(
            text("SELECT COUNT(*) FROM public.eia_pricing_observations")
        ).scalar_one()

    assert snapshot_count == 2
    assert observation_count == 6


def test_http_failure_preserves_existing_snapshot(
    database_engine: Engine,
    workbook_bytes: dict[str, bytes],
) -> None:
    """A failed download cannot erase previously persisted prices."""

    repository = PostgresEiaPricingSnapshotRepository(engine=database_engine)

    with make_http_client(workbook_bytes) as client:
        original_result = make_coordinator(
            client=client,
            engine=database_engine,
        ).refresh(EIA_CALIFORNIA_REGION)

    assert original_result.succeeded

    original = repository.get_snapshot(EIA_CALIFORNIA_REGION)
    assert original is not None

    with make_http_client(
        workbook_bytes,
        failing_region="SCA",
    ) as client:
        failed_result = make_coordinator(
            client=client,
            engine=database_engine,
            refreshed_at=REFRESHED_AT + timedelta(hours=1),
        ).refresh(EIA_CALIFORNIA_REGION)

    assert failed_result.status is EiaRefreshStatus.FAILED
    assert failed_result.failure_reason is (EiaRefreshFailureReason.DOWNLOAD_FAILED)

    restored = repository.get_snapshot(EIA_CALIFORNIA_REGION)

    assert restored is not None
    assert restored.refreshed_at == original.refreshed_at
    assert restored.quotes == original.quotes


def test_invalid_xls_preserves_existing_snapshot(
    database_engine: Engine,
    workbook_bytes: dict[str, bytes],
) -> None:
    """Malformed HTTP content never replaces a valid snapshot."""

    repository = PostgresEiaPricingSnapshotRepository(engine=database_engine)

    with make_http_client(workbook_bytes) as client:
        initial = make_coordinator(
            client=client,
            engine=database_engine,
        ).refresh(EIA_US_REGION)

    assert initial.succeeded

    original = repository.get_snapshot(EIA_US_REGION)
    assert original is not None

    with make_http_client(
        workbook_bytes,
        malformed_region="NUS",
    ) as client:
        result = make_coordinator(
            client=client,
            engine=database_engine,
        ).refresh(EIA_US_REGION)

    assert result.status is EiaRefreshStatus.FAILED
    assert result.failure_reason is (EiaRefreshFailureReason.DOWNLOAD_FAILED)

    restored = repository.get_snapshot(EIA_US_REGION)

    assert restored is not None
    assert restored.refreshed_at == original.refreshed_at
    assert restored.quotes == original.quotes


def test_identical_workbook_can_refresh_timestamp(
    database_engine: Engine,
    workbook_bytes: dict[str, bytes],
) -> None:
    """Repeated publication refresh does not duplicate observations."""

    with make_http_client(workbook_bytes) as client:
        first = make_coordinator(
            client=client,
            engine=database_engine,
        ).refresh(EIA_CALIFORNIA_REGION)

        second_time = REFRESHED_AT + timedelta(hours=1)

        second = make_coordinator(
            client=client,
            engine=database_engine,
            refreshed_at=second_time,
        ).refresh(EIA_CALIFORNIA_REGION)

    assert first.succeeded
    assert second.succeeded

    assert_roundtrip_matches_workbook(
        region=EIA_CALIFORNIA_REGION,
        workbook_bytes=workbook_bytes["SCA"],
        engine=database_engine,
        refreshed_at=second_time,
    )

    with database_engine.connect() as connection:
        observation_count = connection.execute(
            text("SELECT COUNT(*) FROM public.eia_pricing_observations")
        ).scalar_one()

    assert observation_count == 3
