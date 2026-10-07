"""Build a PostgreSQL engine for RouteValue application requests."""

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

from routevalue.infrastructure.persistence.config import (
    DatabaseConfigurationError,
    load_database_url,
)


def create_application_engine(
    *,
    url: URL | None = None,
) -> Engine:
    """Build a conservative pooled engine without opening a connection."""

    selected_url = load_database_url("DATABASE_URL") if url is None else url

    if selected_url.drivername != "postgresql+psycopg":
        raise DatabaseConfigurationError("Application database must use PostgreSQL/Psycopg 3")

    return create_engine(
        selected_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=3,
        pool_timeout=10,
        pool_recycle=300,
    )
