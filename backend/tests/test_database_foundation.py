"""Tests for RouteValue's database configuration and engine foundation."""

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.pool import QueuePool

from routevalue.infrastructure.persistence.config import (
    DatabaseConfigurationError,
    load_database_url,
)
from routevalue.infrastructure.persistence.connection import (
    create_application_engine,
)


@pytest.mark.parametrize(
    "scheme",
    ["postgres", "postgresql", "postgresql+psycopg"],
)
def test_database_url_uses_psycopg_3_and_preserves_connection_details(
    scheme: str,
) -> None:
    url = load_database_url(
        "DATABASE_URL",
        environment={
            "DATABASE_URL": (
                f"{scheme}://routevalue:p%40ss@localhost:5432/routevalue?sslmode=require"
            )
        },
    )

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "routevalue"
    assert url.password == "p@ss"
    assert url.host == "localhost"
    assert url.port == 5432
    assert url.database == "routevalue"
    assert url.query["sslmode"] == "require"
    assert "p@ss" not in str(url)


def test_unpooled_url_does_not_require_application_url() -> None:
    url = load_database_url(
        "DATABASE_URL_UNPOOLED",
        environment={
            "DATABASE_URL_UNPOOLED": ("postgresql://routevalue:secret@db.example/routevalue")
        },
    )

    assert url.host == "db.example"
    assert url.drivername == "postgresql+psycopg"


@pytest.mark.parametrize(
    "raw_url",
    [None, "", "  "],
)
def test_missing_application_url_is_rejected(
    raw_url: str | None,
) -> None:
    environment = {} if raw_url is None else {"DATABASE_URL": raw_url}

    with pytest.raises(
        DatabaseConfigurationError,
        match="DATABASE_URL must be configured",
    ):
        load_database_url(
            "DATABASE_URL",
            environment=environment,
        )


@pytest.mark.parametrize(
    "raw_url",
    [
        "not-a-url",
        "sqlite:///routevalue.db",
        "postgresql+psycopg2://user:secret@localhost/routevalue",
        "postgresql:///routevalue",
        "postgresql://user:secret@localhost",
        "postgresql://user:secret@localhost:bad/routevalue",
    ],
)
def test_invalid_database_url_is_rejected_without_echoing_credentials(
    raw_url: str,
) -> None:
    with pytest.raises(DatabaseConfigurationError) as exc_info:
        load_database_url(
            "DATABASE_URL",
            environment={"DATABASE_URL": raw_url},
        )

    assert "secret" not in str(exc_info.value)
    assert "DATABASE_URL" in str(exc_info.value)


def test_application_engine_uses_postgresql_without_opening_connection() -> None:
    url = load_database_url(
        "DATABASE_URL",
        environment={"DATABASE_URL": ("postgresql://routevalue:secret@localhost/routevalue")},
    )

    engine = create_application_engine(url=url)

    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
        assert engine.url.host == "localhost"

        assert isinstance(engine.pool, QueuePool)
        assert engine.pool.size() == 2

    finally:
        engine.dispose()


def test_application_engine_rejects_other_sql_dialects() -> None:
    with pytest.raises(
        DatabaseConfigurationError,
        match="PostgreSQL/Psycopg 3",
    ):
        create_application_engine(url=make_url("sqlite:///routevalue.db"))


def test_application_engine_requires_configuration_when_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "DATABASE_URL",
        raising=False,
    )

    with pytest.raises(
        DatabaseConfigurationError,
        match="DATABASE_URL must be configured",
    ):
        create_application_engine()
