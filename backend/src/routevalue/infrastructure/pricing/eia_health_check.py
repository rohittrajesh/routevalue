"""Read-only persisted EIA freshness check for operators and scheduled monitors.

Does not download prices, refresh timestamps, create tables or mutate accounts.
Returns exit 0 only when every supported region/grade is usable at the current
time. Prints only region IDs, states and source observation/refresh timestamps.
"""

import json
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from routevalue.infrastructure.persistence.config import (
    DatabaseConfigurationError,
    load_database_url,
)
from routevalue.infrastructure.persistence.connection import create_application_engine
from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    EiaPricingPersistenceError,
    PostgresEiaPricingSnapshotRepository,
)
from routevalue.infrastructure.pricing.eia_geography import EIA_CALIFORNIA_REGION, EIA_US_REGION
from routevalue.infrastructure.pricing.eia_release_policy import is_eia_weekly_quote_fresh
from routevalue.infrastructure.pricing.eia_snapshot_price_provider import EiaSnapshotReader


def pricing_health(reader: EiaSnapshotReader, *, as_of: datetime) -> dict[str, object]:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("health check time must be timezone aware")
    regions: list[dict[str, object]] = []
    healthy = True
    for region in (EIA_CALIFORNIA_REGION, EIA_US_REGION):
        item: dict[str, object] = {"region_id": region.geography.region_id}
        try:
            snapshot = reader.get_snapshot(region)
        except (EiaPricingPersistenceError, SQLAlchemyError):
            item["status"] = "unavailable"
            healthy = False
        else:
            if snapshot is None:
                item["status"] = "missing"
                healthy = False
            else:
                unusable = [
                    quote.fuel_grade.value
                    for quote in snapshot.quotes
                    if not is_eia_weekly_quote_fresh(quote, as_of)
                ]
                # A future refresh indicates clock/data corruption even when the
                # quote's observation alone is old enough to look valid.
                future_refresh = snapshot.refreshed_at > as_of
                item.update(
                    status="unusable" if unusable or future_refresh else "healthy",
                    unusable_grades=unusable,
                    future_refresh=future_refresh,
                    observed_at={
                        quote.fuel_grade.value: quote.observed_at.isoformat()
                        if quote.observed_at is not None
                        else None
                        for quote in snapshot.quotes
                    },
                    refreshed_at=snapshot.refreshed_at.isoformat(),
                )
                healthy = healthy and not unusable and not future_refresh
        regions.append(item)
    return {"healthy": healthy, "checked_at": as_of.isoformat(), "regions": regions}


def main() -> int:
    try:
        engine = create_application_engine(url=load_database_url("DATABASE_URL_UNPOOLED"))
    except DatabaseConfigurationError:
        print(json.dumps({"healthy": False, "error": "database_configuration_unavailable"}))
        return 2
    try:
        report = pricing_health(
            PostgresEiaPricingSnapshotRepository(engine=engine), as_of=datetime.now(UTC)
        )
        print(json.dumps(report, indent=2))
        return 0 if report["healthy"] else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
