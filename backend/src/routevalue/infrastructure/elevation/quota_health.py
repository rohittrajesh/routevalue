"""Read-only shared terrain quota health; never reserves or calls providers."""

from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from routevalue.infrastructure.elevation.safety import PublicElevationPolicy
from routevalue.infrastructure.persistence.schema import elevation_call_reservations as calls


def shared_quota_health(engine: Engine, policy: PublicElevationPolicy) -> dict[str, object]:
    """Inspect permissions and DB-clock usage without changing accounting history."""
    report: dict[str, object] = {
        "status": "unavailable",
        "provider_calls": 0,
        "quota_writes": 0,
        "daily_limit": policy.max_requests_per_24_hours,
        "requests_per_trip": policy.max_requests_per_trip,
        "minimum_interval_seconds": policy.minimum_interval_seconds,
    }
    try:
        with engine.begin() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '5s'"))
            privileges = connection.execute(
                text(
                    "SELECT has_table_privilege(current_user, 'public.elevation_call_reservations', 'SELECT'), "
                    "has_table_privilege(current_user, 'public.elevation_call_reservations', 'INSERT'), "
                    "has_table_privilege(current_user, 'public.elevation_call_reservations', 'DELETE')"
                )
            ).one()
            if not all(privileges):
                return {**report, "status": "permission_denied"}
            now: datetime = connection.execute(select(func.clock_timestamp())).scalar_one()
            count, latest = connection.execute(
                select(func.count(), func.max(calls.c.reserved_at)).where(
                    calls.c.reserved_at > now - timedelta(days=1)
                )
            ).one()
        report.update(
            active_reservations=count,
            remaining_requests=max(0, policy.max_requests_per_24_hours - count),
            checked_at=now.isoformat(),
            latest_reservation_at=latest.isoformat() if latest is not None else None,
            status=(
                "future_reservation"
                if latest is not None and latest > now
                else "exhausted"
                if count >= policy.max_requests_per_24_hours
                else "ready"
            ),
        )
    except SQLAlchemyError:
        # Never emit SQLAlchemy diagnostics containing connection or statement data.
        pass
    return report
