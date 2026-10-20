"""Validate an explicitly reviewed production target; never infer a default branch."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.engine import URL, Engine

from routevalue.infrastructure.auth.neon_config import (
    NeonAuthConfigurationError,
    load_neon_jwt_settings,
)
from routevalue.infrastructure.persistence.config import load_database_url
from routevalue.infrastructure.pricing.eia_v2_development_refresh import (
    _DEVELOPMENT_AUTH_HOST,
    _DEVELOPMENT_DATABASE_HOST,
)

RELEASE_SCHEMA = "d41e7a902b63"


@dataclass(frozen=True, slots=True)
class ProductionTarget:
    branch: str
    database_host: str
    database: str
    role: str
    auth_url: str
    jwks_url: str


def load_production_target(path: Path) -> ProductionTarget:
    if path.stat().st_size > 4096:
        raise ValueError("invalid release target")
    value = json.loads(path.read_text())
    if (
        not isinstance(value, dict)
        or set(value) != {"branch", "database_host", "database", "role", "auth_url", "jwks_url"}
        or any(not isinstance(item, str) or not item.strip() for item in value.values())
    ):
        raise ValueError("invalid release target")
    target = ProductionTarget(**value)
    if target.role != "routevalue_prod_app":
        raise ValueError("production operations require the limited runtime role")
    if target.branch != "v2-production-routevalue":
        raise ValueError("only the explicitly designated V2 production branch is supported")
    if (
        not target.database_host.endswith(".neon.tech")
        or "-pooler" in target.database_host
        or target.database_host == _DEVELOPMENT_DATABASE_HOST
        or any(character in target.database_host for character in "/:@?#\\")
    ):
        raise ValueError("invalid production database host")
    try:
        settings = load_neon_jwt_settings(
            environment={
                "NEON_AUTH_BASE_URL": target.auth_url,
                "NEON_AUTH_JWKS_URL": target.jwks_url,
            }
        )
    except NeonAuthConfigurationError:
        raise ValueError("invalid production authentication target") from None
    auth = urlsplit(target.auth_url)
    if (
        auth.hostname == _DEVELOPMENT_AUTH_HOST
        or not settings.jwks_url.startswith(target.auth_url.rstrip("/") + "/")
        or auth.path.rstrip("/") != f"/{target.database}/auth"
    ):
        raise ValueError("invalid production authentication target")
    return target


def validated_production_url(values: Mapping[str, str], target: ProductionTarget) -> URL:
    direct = load_database_url("DATABASE_URL_UNPOOLED", environment=values)
    pooled = load_database_url("DATABASE_URL", environment=values)
    first, suffix = target.database_host.split(".", 1)
    for url, hosts in (
        (direct, {target.database_host}),
        (pooled, {target.database_host, f"{first}-pooler.{suffix}"}),
    ):
        if (
            url.host not in hosts
            or url.database != target.database
            or url.username != target.role
            or not url.password
            or url.query.get("sslmode") != "require"
            or url.port not in (None, 5432)
        ):
            raise ValueError("database does not match reviewed production target")
    if (
        values.get("NEON_AUTH_BASE_URL", "").rstrip("/") != target.auth_url.rstrip("/")
        or values.get("NEON_AUTH_JWKS_URL") != target.jwks_url
    ):
        raise ValueError("authentication does not match reviewed production target")
    load_neon_jwt_settings(environment=values)
    return direct


def verify_production_database(engine: Engine, target: ProductionTarget) -> None:
    with engine.connect() as connection:
        connection.execute(text("SET LOCAL statement_timeout = '5s'"))
        database, role = connection.execute(text("SELECT current_database(), current_user")).one()
        revision = connection.execute(
            text("SELECT version_num FROM public.alembic_version")
        ).scalar_one()
        tables = connection.execute(
            text(
                "SELECT to_regclass('public.eia_pricing_snapshots'), "
                "to_regclass('public.eia_pricing_observations'), "
                "to_regclass('public.eia_refresh_attempts'), "
                "to_regclass('public.elevation_call_reservations')"
            )
        ).one()
    if (
        database != target.database
        or role != target.role
        or revision != RELEASE_SCHEMA
        or any(table is None for table in tables)
    ):
        raise ValueError("production database identity or schema check failed")
