"""Offline checks for RouteValue's Alembic migration foundation."""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Column, Integer, Table

from routevalue.infrastructure.persistence.schema import (
    include_routevalue_name,
    metadata,
)


@pytest.mark.parametrize("schema_name", [None, "public"])
def test_migration_filter_allows_public_schema(
    schema_name: str | None,
) -> None:
    assert include_routevalue_name(schema_name, "schema", {})


@pytest.mark.parametrize(
    "schema_name",
    ["neon_auth", "private", "other"],
)
def test_migration_filter_excludes_nonbusiness_schemas(
    schema_name: str,
) -> None:
    assert not include_routevalue_name(schema_name, "schema", {})


def test_migration_filter_excludes_unowned_public_tables() -> None:
    assert not include_routevalue_name(
        "unrelated_table",
        "table",
        {"schema_name": "public"},
    )


def test_migration_filter_includes_owned_public_tables_only() -> None:
    table = Table(
        "test_owned_table",
        metadata,
        Column("id", Integer),
    )

    try:
        assert include_routevalue_name(
            "test_owned_table",
            "table",
            {"schema_name": "public"},
        )

        assert include_routevalue_name(
            "test_owned_table",
            "table",
            {"schema_name": None},
        )

        assert not include_routevalue_name(
            "test_owned_table",
            "table",
            {"schema_name": "neon_auth"},
        )

    finally:
        metadata.remove(table)


def test_metadata_targets_public_business_schema() -> None:
    assert metadata.schema == "public"


def test_alembic_discovers_revision_directory_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)

    backend_root = Path(__file__).resolve().parents[1]

    config = Config(str(backend_root / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)

    assert Path(scripts.dir).resolve() == backend_root / "migrations"
    assert Path(scripts.versions).is_dir()
    assert config.get_main_option("sqlalchemy.url") is None
    assert isinstance(scripts.get_heads(), list)
