"""M8 integration tests for the explicit EIA refresh CLI.

Runs the real job entry point and PostgreSQL persistence against
the isolated local M8 database.

HTTP responses are supplied through MockTransport using previously
downloaded EIA XLS workbooks. No live EIA requests are performed.
"""

import os
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, delete, text
from sqlalchemy.engine import Engine, make_url

from routevalue.infrastructure.persistence.schema import (
    eia_pricing_observations,
    eia_pricing_snapshots,
)
from routevalue.infrastructure.pricing import (
    eia_refresh_job as job_module,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
)

FIXTURES = {
    "SCA": Path("/tmp/routevalue_eia_california.xls"),
    "NUS": Path("/tmp/routevalue_eia_gasoline.xls"),
}

XLS_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@pytest.fixture
def database_engine() -> Iterator[Engine]:
    """Use only the existing isolated M8 PostgreSQL database."""

    raw_url = os.environ.get("DATABASE_URL_UNPOOLED")

    if raw_url is None:
        pytest.fail("DATABASE_URL_UNPOOLED must be configured for G8")

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
            database, username = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()

            revision = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar_one()

            assert database == "routevalue_m8_eia_test"
            assert username == "routevalue_local"
            assert revision == "d41e7a902b63"

        clean()
        yield engine

    finally:
        try:
            clean()
        finally:
            engine.dispose()


@pytest.fixture
def workbooks() -> dict[str, bytes]:
    """Load authentic EIA XLS content from local fixtures."""

    loaded: dict[str, bytes] = {}

    for region_id, path in FIXTURES.items():
        if not path.is_file():
            pytest.fail(f"Missing workbook fixture: {path}")

        content = path.read_bytes()

        assert content.startswith(XLS_SIGNATURE)
        loaded[region_id] = content

    return loaded


def install_mock_http(
    monkeypatch: pytest.MonkeyPatch,
    workbooks: dict[str, bytes],
    *,
    failing_region: str | None = None,
) -> list[httpx.Client]:
    """Replace only the job module's HTTP client factory.

    The real downloader still receives a genuine httpx.Client.
    Every request is served by MockTransport.
    """

    created_clients: list[httpx.Client] = []

    def respond(request: httpx.Request) -> httpx.Response:
        url = str(request.url)

        for region in (
            EIA_CALIFORNIA_REGION,
            EIA_US_REGION,
        ):
            if url != region.workbook_url:
                continue

            region_id = region.geography.region_id

            if region_id == failing_region:
                return httpx.Response(503)

            return httpx.Response(
                200,
                content=workbooks[region_id],
            )

        return httpx.Response(404)

    def make_client(
        *,
        follow_redirects: bool = False,
    ) -> httpx.Client:
        client = httpx.Client(
            transport=httpx.MockTransport(respond),
            follow_redirects=follow_redirects,
        )

        created_clients.append(client)
        return client

    monkeypatch.setattr(
        job_module,
        "httpx",
        SimpleNamespace(Client=make_client),
    )

    return created_clients


def read_counts(engine: Engine) -> tuple[int, int]:
    """Count committed snapshot headers and observations."""

    with engine.connect() as connection:
        snapshots = connection.execute(
            text("SELECT COUNT(*) FROM public.eia_pricing_snapshots")
        ).scalar_one()

        observations = connection.execute(
            text("SELECT COUNT(*) FROM public.eia_pricing_observations")
        ).scalar_one()

    return snapshots, observations


def test_cli_refreshes_both_regions(
    database_engine: Engine,
    workbooks: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The actual CLI persists both EIA regions successfully."""

    clients = install_mock_http(monkeypatch, workbooks)

    status = job_module.main(["--execute", "--region", "all"])

    assert status == 0
    assert read_counts(database_engine) == (2, 6)

    with database_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT region_id, COUNT(*) "
                "FROM public.eia_pricing_observations "
                "GROUP BY region_id "
                "ORDER BY region_id"
            )
        ).all()

    assert [tuple(row) for row in rows] == [
        ("NUS", 3),
        ("SCA", 3),
    ]
    assert len(clients) == 1
    assert clients[0].is_closed


def test_cli_refreshes_only_requested_region(
    database_engine: Engine,
    workbooks: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A California-only run must not write national pricing."""

    clients = install_mock_http(monkeypatch, workbooks)

    status = job_module.main(["--execute", "--region", "california"])

    assert status == 0
    assert read_counts(database_engine) == (1, 3)

    with database_engine.connect() as connection:
        region_ids = (
            connection.execute(text("SELECT region_id FROM public.eia_pricing_snapshots"))
            .scalars()
            .all()
        )

    assert region_ids == ["SCA"]
    assert len(clients) == 1
    assert clients[0].is_closed


def test_cli_partial_failure_returns_nonzero(
    database_engine: Engine,
    workbooks: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed California download does not block national success."""

    clients = install_mock_http(
        monkeypatch,
        workbooks,
        failing_region="SCA",
    )

    status = job_module.main(["--execute", "--region", "all"])

    assert status == 1
    assert read_counts(database_engine) == (1, 3)

    with database_engine.connect() as connection:
        regions = (
            connection.execute(text("SELECT region_id FROM public.eia_pricing_snapshots"))
            .scalars()
            .all()
        )

    assert regions == ["NUS"]
    assert len(clients) == 1
    assert clients[0].is_closed


def test_cli_failed_refresh_preserves_previous_prices(
    database_engine: Engine,
    workbooks: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later failed refresh cannot erase committed observations."""

    install_mock_http(monkeypatch, workbooks)

    first_status = job_module.main(["--execute", "--region", "california"])

    assert first_status == 0

    with database_engine.connect() as connection:
        original_rows = connection.execute(
            text(
                "SELECT fuel_grade, series_id, "
                "observed_at, price_per_gallon "
                "FROM public.eia_pricing_observations "
                "WHERE region_id = 'SCA' "
                "ORDER BY fuel_grade"
            )
        ).all()

    assert len(original_rows) == 3

    clients = install_mock_http(
        monkeypatch,
        workbooks,
        failing_region="SCA",
    )

    second_status = job_module.main(["--execute", "--region", "california"])

    assert second_status == 1

    with database_engine.connect() as connection:
        restored_rows = connection.execute(
            text(
                "SELECT fuel_grade, series_id, "
                "observed_at, price_per_gallon "
                "FROM public.eia_pricing_observations "
                "WHERE region_id = 'SCA' "
                "ORDER BY fuel_grade"
            )
        ).all()

    assert restored_rows == original_rows
    assert read_counts(database_engine) == (1, 3)
    assert clients[-1].is_closed


def test_cli_without_execute_never_creates_http_client(
    database_engine: Engine,
    workbooks: dict[str, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI must not access pricing infrastructure without consent."""

    clients = install_mock_http(monkeypatch, workbooks)

    status = job_module.main(["--region", "all"])

    assert status == 2
    assert clients == []
    assert read_counts(database_engine) == (0, 0)
