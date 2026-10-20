"""Explicit, local-only EIA gasoline pricing refresh job.

Run manually with:
    python -m routevalue.infrastructure.pricing.eia_refresh_job --execute

This module does not register an API route, startup hook, or scheduler.
"""

import argparse
import logging
import os
from collections.abc import Sequence

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    PostgresEiaPricingSnapshotRepository,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_refresh_advisory_lock import (
    hold_eia_refresh_lock,
)
from routevalue.infrastructure.pricing.eia_refresh_coordinator import (
    EiaRefreshCoordinator,
)
from routevalue.infrastructure.pricing.eia_refresh_diagnostics import (
    EiaObservedRefreshRunner,
)
from routevalue.infrastructure.pricing.eia_refresh_http_adapter import (
    EiaWorkbookFetcher,
)
from routevalue.infrastructure.pricing.eia_refresh_singleflight import (
    EiaSingleFlightRefreshRunner,
)

_LOGGER = logging.getLogger(__name__)

_REGIONS: dict[str, EiaGasolineRegion] = {
    "california": EIA_CALIFORNIA_REGION,
    "national": EIA_US_REGION,
}


def _validated_local_url() -> str:
    """Accept only the isolated local M8 PostgreSQL database."""

    raw_url = os.environ.get("DATABASE_URL_UNPOOLED")

    if not raw_url:
        raise ValueError("DATABASE_URL_UNPOOLED is not configured")

    url = make_url(raw_url)

    if not (
        url.drivername == "postgresql+psycopg"
        and url.host == "127.0.0.1"
        and url.port == 55432
        and url.username == "routevalue_local"
        and url.database == "routevalue_m8_eia_test"
    ):
        raise ValueError("refresh job requires isolated local M8 database")

    return raw_url


def _verify_database(engine: Engine) -> None:
    """Verify database identity and expected schema revision."""

    with engine.connect() as connection:
        database, username = connection.execute(
            text("SELECT current_database(), current_user")
        ).one()

        version = connection.execute(
            text("SELECT version_num FROM public.alembic_version")
        ).scalar_one()

    if (
        database != "routevalue_m8_eia_test"
        or username != "routevalue_local"
        or version not in ("e8a1d4c209bf", "f2b7c39a106d")
    ):
        raise ValueError("isolated M8 database identity check failed")


def run_refreshes(
    *,
    engine: Engine,
    client: httpx.Client,
    regions: Sequence[EiaGasolineRegion],
) -> int:
    """Execute explicitly requested refreshes.

    Return zero only when every requested region was persisted.
    Caller owns the HTTP client and database engine.

    Cross-process locking is managed by main(), not this function.
    """

    repository = PostgresEiaPricingSnapshotRepository(engine=engine)

    coordinator = EiaRefreshCoordinator(
        fetch_workbook=EiaWorkbookFetcher(client=client),
        repository=repository,
    )

    runner = EiaObservedRefreshRunner(
        coordinator=EiaSingleFlightRefreshRunner(coordinator=coordinator)
    )

    all_succeeded = True

    for region in regions:
        try:
            result = runner.refresh(region)
        except Exception as exc:  # noqa: BLE001
            # CLI isolation boundary: classify unexpected failures
            # without logging sensitive exception messages.
            _LOGGER.error(
                "eia_refresh_job_exception region_id=%s exception_type=%s",
                region.geography.region_id,
                type(exc).__name__,
            )
            all_succeeded = False
            continue

        if not result.succeeded:
            all_succeeded = False

    return 0 if all_succeeded else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Execute a manually authorized, cross-process-safe refresh."""

    parser = argparse.ArgumentParser(description="Manually refresh local EIA gasoline prices.")

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Explicitly permit live EIA workbook downloads.",
    )

    parser.add_argument(
        "--region",
        choices=("california", "national", "all"),
        default="all",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if not args.execute:
        parser.print_help()
        return 2

    if args.region == "all":
        regions = tuple(_REGIONS.values())
    else:
        regions = (_REGIONS[args.region],)

    engine: Engine | None = None

    try:
        raw_url = _validated_local_url()

        engine = create_engine(
            raw_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10},
        )

        _verify_database(engine)

        # The advisory lock must be acquired before opening an
        # HTTP client. It stays held across every requested region.
        #
        # The lock's PostgreSQL connection remains checked out
        # until all refresh operations have finished.
        with hold_eia_refresh_lock(engine), httpx.Client(follow_redirects=False) as client:
            return run_refreshes(
                engine=engine,
                client=client,
                regions=regions,
            )

    except Exception as exc:  # noqa: BLE001
        # Final CLI boundary: fail closed. Do not log raw
        # exception messages or database connection strings.
        _LOGGER.error(
            "eia_refresh_job_setup_failed exception_type=%s",
            type(exc).__name__,
        )
        return 1

    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
