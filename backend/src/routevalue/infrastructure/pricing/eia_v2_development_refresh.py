"""Explicit, pinned-branch EIA refresh for RouteValue V2 development.

This does not modify the M8 local-only refresh CLI. This module is not
registered with FastAPI, a scheduler, or application startup.

Run from backend/ with .env.v2.local loaded into this process's environment.
First run --check. Running --execute requires an additional branch confirmation.
"""

import argparse
import logging
import os
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

from routevalue.infrastructure.persistence.config import load_database_url
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_refresh_advisory_lock import hold_eia_refresh_lock
from routevalue.infrastructure.pricing.eia_refresh_job import run_refreshes

_LOGGER = logging.getLogger(__name__)

# RouteValue's specific existing Neon development branch.
# Deliberately not configurable from an environment variable or CLI flag.
# If this branch is replaced, review and update these values before reuse.
_DEVELOPMENT_BRANCH = "v2-development-routevalue"
_DEVELOPMENT_DATABASE_HOST = "ep-lucky-meadow-ark81i54.c-4.us-west-2.aws.neon.tech"
_DEVELOPMENT_AUTH_HOST = "ep-lucky-meadow-ark81i54.neonauth.c-4.us-west-2.aws.neon.tech"
_DEVELOPMENT_DATABASE = "neondb"
_DEVELOPMENT_USER = "neondb_owner"
_REQUIRED_REVISION = "e8a1d4c209bf"

_REGIONS: dict[str, tuple[EiaGasolineRegion, ...]] = {
    "california": (EIA_CALIFORNIA_REGION,),
    "national": (EIA_US_REGION,),
    "all": (EIA_CALIFORNIA_REGION, EIA_US_REGION),
}


def _validated_development_url(values: Mapping[str, str]) -> URL:
    """Pin BOTH Neon Postgres and Auth to the known V2 development branch."""

    url = load_database_url("DATABASE_URL_UNPOOLED", environment=values)

    if (
        url.host != _DEVELOPMENT_DATABASE_HOST
        or url.database != _DEVELOPMENT_DATABASE
        or url.username != _DEVELOPMENT_USER
        or not url.password
        or url.port not in (None, 5432)
        or url.query.get("sslmode") != "require"
        or "-pooler" in url.host
    ):
        raise ValueError("not the pinned, unpooled V2 Neon development database")

    auth_raw = values.get("NEON_AUTH_BASE_URL", "")
    try:
        auth = urlsplit(auth_raw)
        _ = auth.port
    except ValueError:
        raise ValueError("invalid V2 development Auth configuration") from None

    if (
        auth.scheme != "https"
        or auth.hostname != _DEVELOPMENT_AUTH_HOST
        or auth.port is not None
        or auth.path.rstrip("/") != "/neondb/auth"
        or auth.username is not None
        or auth.password is not None
        or auth.query
        or auth.fragment
    ):
        raise ValueError("not the pinned V2 Neon development Auth branch")

    return url


def _verify_database(engine: Engine) -> None:
    """Check connected role, database, migration and EIA schema before any write."""

    with engine.connect() as connection:
        database, user = connection.execute(text("SELECT current_database(), current_user")).one()
        revision = connection.execute(
            text("SELECT version_num FROM public.alembic_version")
        ).scalar_one()
        tables = connection.execute(
            text(
                "SELECT to_regclass('public.eia_pricing_snapshots'), "
                "to_regclass('public.eia_pricing_observations')"
            )
        ).one()

    if (
        database != _DEVELOPMENT_DATABASE
        or user != _DEVELOPMENT_USER
        or revision != _REQUIRED_REVISION
        or any(table is None for table in tables)
    ):
        raise ValueError("V2 development database identity or schema check failed")


def _print_snapshot_status(engine: Engine) -> None:
    """Display metadata only; do not dump credentials or price data."""

    with engine.connect() as connection:
        snapshots = connection.execute(
            text("SELECT COUNT(*) FROM public.eia_pricing_snapshots")
        ).scalar_one()
        observations = connection.execute(
            text("SELECT COUNT(*) FROM public.eia_pricing_observations")
        ).scalar_one()
    print(f"Development EIA snapshots: {snapshots}")
    print(f"Development EIA observations: {observations}")


def main(argv: Sequence[str] | None = None) -> int:
    """Safely check or manually refresh the pinned Neon dev-branch EIA data."""

    parser = argparse.ArgumentParser(description="V2 development-branch-only EIA refresh")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="Read-only identity/data check")
    action.add_argument("--execute", action="store_true", help="Fetch and persist EIA data")
    parser.add_argument("--region", choices=tuple(_REGIONS), default="all")
    parser.add_argument(
        "--confirm-development-branch",
        help="Must equal v2-development-routevalue when executing a refresh",
    )
    args = parser.parse_args(argv)

    # Refuse all write operations without explicit human confirmation.
    if args.execute and args.confirm_development_branch != _DEVELOPMENT_BRANCH:
        parser.error("--execute requires --confirm-development-branch v2-development-routevalue")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    engine: Engine | None = None
    try:
        url = _validated_development_url(os.environ)
        engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10},
        )
        _verify_database(engine)
        print("Verified target: pinned V2 development branch (not production)")
        _print_snapshot_status(engine)

        if args.check:
            print("Read-only check complete. No HTTP download or database writes performed.")
            return 0

        # All guards pass BEFORE EIA HTTP client construction or any write.
        with hold_eia_refresh_lock(engine), httpx.Client(follow_redirects=False) as client:
            result = run_refreshes(
                engine=engine,
                client=client,
                regions=_REGIONS[args.region],
            )

        _print_snapshot_status(engine)
        return result

    except Exception as exc:  # noqa: BLE001
        # Intentionally avoid exception messages (which may contain DB URLs).
        _LOGGER.error(
            "v2_development_eia_refresh_failed exception_type=%s",
            type(exc).__name__,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
