"""Validate database connection URLs without exposing credentials."""

import os
from collections.abc import Mapping
from typing import Literal

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

DatabaseURLVariable = Literal["DATABASE_URL", "DATABASE_URL_UNPOOLED"]

_ALLOWED_DRIVERS = frozenset(
    {
        "postgres",
        "postgresql",
        "postgresql+psycopg",
    }
)


class DatabaseConfigurationError(RuntimeError):
    """A required database URL is missing or invalid."""


def load_database_url(
    variable: DatabaseURLVariable,
    *,
    environment: Mapping[str, str] | None = None,
) -> URL:
    """Load one PostgreSQL URL and select the explicit Psycopg 3 driver."""

    values = os.environ if environment is None else environment

    raw_url = values.get(variable)

    if raw_url is None or not raw_url.strip():
        raise DatabaseConfigurationError(f"{variable} must be configured")

    try:
        parsed_url = make_url(raw_url.strip())
        _ = parsed_url.port
    except (ArgumentError, ValueError):
        raise DatabaseConfigurationError(f"{variable} must be a valid PostgreSQL URL") from None

    if parsed_url.drivername not in _ALLOWED_DRIVERS:
        raise DatabaseConfigurationError(f"{variable} must use PostgreSQL with Psycopg 3")

    if not parsed_url.username or not parsed_url.host or not parsed_url.database:
        raise DatabaseConfigurationError(
            f"{variable} must include a username, hostname, and database name"
        )

    return parsed_url.set(drivername="postgresql+psycopg")
