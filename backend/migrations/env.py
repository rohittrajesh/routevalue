"""Alembic migration environment for RouteValue-owned business tables."""

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from routevalue.infrastructure.persistence.config import load_database_url
from routevalue.infrastructure.persistence.schema import (
    include_routevalue_name,
    metadata,
)


def run_migrations_offline() -> None:
    """Generate PostgreSQL migration SQL without connecting to a database."""

    context.configure(
        dialect_name="postgresql",
        target_metadata=metadata,
        literal_binds=True,
        include_schemas=True,
        include_name=include_routevalue_name,
        version_table_schema="public",
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations using a direct PostgreSQL connection."""

    engine = create_engine(
        load_database_url("DATABASE_URL_UNPOOLED"),
        poolclass=NullPool,
        connect_args={
            "options": "-csearch_path=pg_catalog",
        },
    )

    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=metadata,
                include_schemas=True,
                include_name=include_routevalue_name,
                version_table_schema="public",
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()

    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
