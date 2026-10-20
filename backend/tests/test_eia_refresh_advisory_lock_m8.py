"""M8 cross-connection advisory lock safety tests."""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from routevalue.infrastructure.pricing.eia_refresh_advisory_lock import (
    EIA_REFRESH_LOCK_KEY,
    EiaRefreshLockUnavailableError,
    hold_eia_refresh_lock,
)


@pytest.fixture
def engine() -> Iterator[Engine]:
    raw_url = os.environ.get("DATABASE_URL_UNPOOLED")

    if not raw_url:
        pytest.fail("M8 test database URL is required")

    url = make_url(raw_url)

    assert url.drivername == "postgresql+psycopg"
    assert url.host == "127.0.0.1"
    assert url.port == 55432
    assert url.username == "routevalue_local"
    assert url.database == "routevalue_m8_eia_test"

    database_engine = create_engine(
        url,
        pool_size=3,
        max_overflow=0,
        pool_pre_ping=True,
    )

    try:
        with database_engine.connect() as connection:
            identity = connection.execute(text("SELECT current_database(), current_user")).one()

            revision = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar_one()

        assert tuple(identity) == (
            "routevalue_m8_eia_test",
            "routevalue_local",
        )
        assert revision == "d41e7a902b63"

        yield database_engine
    finally:
        database_engine.dispose()


def test_lock_can_be_acquired_and_released(
    engine: Engine,
) -> None:
    with hold_eia_refresh_lock(engine):
        with engine.connect() as connection:
            available = connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": EIA_REFRESH_LOCK_KEY},
            ).scalar_one()

        assert available is False

    with hold_eia_refresh_lock(engine):
        pass


def test_second_connection_cannot_acquire_lock(
    engine: Engine,
) -> None:
    with (
        hold_eia_refresh_lock(engine),
        pytest.raises(
            EiaRefreshLockUnavailableError,
            match="already running",
        ),
        hold_eia_refresh_lock(engine),
    ):
        pytest.fail("Overlapping refresh was allowed")


def test_lock_released_after_exception(
    engine: Engine,
) -> None:
    with pytest.raises(RuntimeError, match="simulated failure"), hold_eia_refresh_lock(engine):
        raise RuntimeError("simulated failure")

    with hold_eia_refresh_lock(engine):
        pass


def test_lock_does_not_block_normal_database_transactions(
    engine: Engine,
) -> None:
    with hold_eia_refresh_lock(engine):
        with engine.begin() as connection:
            result = connection.execute(text("SELECT 1")).scalar_one()

        assert result == 1


def test_lock_is_unavailable_on_sqlite() -> None:
    sqlite_engine = create_engine("sqlite+pysqlite:///:memory:")

    try:
        with (
            pytest.raises(ValueError, match="requires PostgreSQL"),
            hold_eia_refresh_lock(sqlite_engine),
        ):
            pass
    finally:
        sqlite_engine.dispose()
