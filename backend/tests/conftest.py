"""Shared pytest fixtures for RouteValue backend integration tests."""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, make_url

from routevalue.infrastructure.persistence.connection import (
    create_application_engine,
)

_TEST_DATABASE_ENV = "ROUTEVALUE_TEST_DATABASE_URL"
_EXPECTED_REVISION = "d41e7a902b63"


@pytest.fixture(scope="session")
def postgres_engine() -> Iterator[Engine]:
    """Connect only to RouteValue's designated disposable PostgreSQL database."""

    raw_url = os.environ.get(_TEST_DATABASE_ENV)

    if not raw_url:
        pytest.skip("Local PostgreSQL integration tests require ROUTEVALUE_TEST_DATABASE_URL")

    url = make_url(raw_url)

    if (
        url.drivername != "postgresql+psycopg"
        or url.host != "127.0.0.1"
        or url.port != 55432
        or url.database != "routevalue_m3b4"
        or url.username != "routevalue_local"
    ):
        pytest.fail(
            "Integration tests may only use the designated local RouteValue PostgreSQL database"
        )

    engine = create_application_engine(url=url)

    try:
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar_one()

            if revision != _EXPECTED_REVISION:
                pytest.fail(
                    "Local test database must be migrated to the expected RouteValue revision"
                )

        yield engine

    finally:
        engine.dispose()


@pytest.fixture
def db_connection(
    postgres_engine: Engine,
) -> Iterator[Connection]:
    """Provide an isolated transaction that always rolls back."""

    with postgres_engine.connect() as connection:
        transaction = connection.begin()

        try:
            yield connection

        finally:
            if transaction.is_active:
                transaction.rollback()
