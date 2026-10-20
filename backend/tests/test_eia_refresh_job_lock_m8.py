"""M8 tests for PostgreSQL advisory locking in the refresh CLI."""

import os
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from routevalue.infrastructure.pricing import (
    eia_refresh_job as job_module,
)
from routevalue.infrastructure.pricing.eia_refresh_advisory_lock import (
    EIA_REFRESH_LOCK_KEY,
    hold_eia_refresh_lock,
)


@pytest.fixture
def engine() -> Iterator[Engine]:
    raw_url = os.environ.get("DATABASE_URL_UNPOOLED")

    if not raw_url:
        pytest.fail("M8 PostgreSQL URL is required")

    url = make_url(raw_url)

    assert url.drivername == "postgresql+psycopg"
    assert url.host == "127.0.0.1"
    assert url.port == 55432
    assert url.username == "routevalue_local"
    assert url.database == "routevalue_m8_eia_test"

    database_engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )

    try:
        with database_engine.connect() as connection:
            database, username = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()

            revision = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar_one()

        assert database == "routevalue_m8_eia_test"
        assert username == "routevalue_local"
        assert revision == "a19d6e2c740b"

        yield database_engine
    finally:
        database_engine.dispose()


def test_contending_cli_does_not_start_http(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second job fails before opening any HTTP client."""

    def forbidden_client(**kwargs: object) -> httpx.Client:
        pytest.fail("HTTP client created while lock was held")

    monkeypatch.setattr(
        httpx,
        "Client",
        forbidden_client,
    )

    with hold_eia_refresh_lock(engine):
        status = job_module.main(["--execute", "--region", "all"])

    assert status == 1


def test_cli_holds_lock_during_refresh(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Another database session cannot enter during the refresh."""

    calls: list[int] = []

    def fake_refreshes(
        *,
        engine: Engine,
        client: httpx.Client,
        regions: object,
    ) -> int:
        assert not client.is_closed

        with engine.connect() as connection:
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": EIA_REFRESH_LOCK_KEY},
            ).scalar_one()

        assert acquired is False
        calls.append(1)
        return 0

    monkeypatch.setattr(
        job_module,
        "run_refreshes",
        fake_refreshes,
    )

    status = job_module.main(["--execute", "--region", "all"])

    assert status == 0
    assert calls == [1]

    with hold_eia_refresh_lock(engine):
        pass


def test_cli_releases_lock_after_failure(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpected refresh exception cannot strand the lock."""

    def failing_refreshes(
        *,
        engine: Engine,
        client: httpx.Client,
        regions: object,
    ) -> int:
        raise RuntimeError("simulated refresh failure")

    monkeypatch.setattr(
        job_module,
        "run_refreshes",
        failing_refreshes,
    )

    status = job_module.main(["--execute", "--region", "california"])

    assert status == 1

    with hold_eia_refresh_lock(engine):
        pass
