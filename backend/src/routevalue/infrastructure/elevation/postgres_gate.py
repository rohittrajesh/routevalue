"""Durable OpenTopoData accounting shared by workers using the same database.

Reservations commit before HTTP, including attempts that later fail. A crash or
uncertain commit can waste allowance, but never permits an unaccounted call.
Only timestamps and random reservation IDs are stored. No runtime DDL occurs.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from routevalue.application.terrain_ports import (
    ElevationProvider,
    ElevationProviderUnavailableError,
)
from routevalue.infrastructure.elevation.safety import (
    ElevationDailyBudgetExceededError,
    GuardedElevationTripProvider,
    PublicElevationPolicy,
)
from routevalue.infrastructure.persistence.schema import elevation_call_reservations as calls

# One provider-wide key: different workers cannot choose separate quota buckets.
_LOCK_KEY = 7284196301206


class PostgresElevationCallGate:
    """Serialize reservations with a PostgreSQL transaction advisory lock.

    All deployments sharing an upstream IP must use this same database. Unrelated
    OpenTopoData consumers remain outside this application's accounting. Database
    unavailability, missing migrations and lock contention fail closed to baseline.
    """

    def __init__(
        self,
        *,
        engine_factory: Callable[[], Engine],
        policy: PublicElevationPolicy,
    ) -> None:
        self.policy = policy
        self._engine_factory = engine_factory

    def new_trip(self, delegate: ElevationProvider) -> GuardedElevationTripProvider:
        return GuardedElevationTripProvider(delegate=delegate, gate=self)

    def reserve(self) -> None:
        try:
            with self._engine_factory().begin() as connection:
                # Bound both contention and a stalled DB; do not retry HTTP or DB.
                connection.execute(text("SET LOCAL lock_timeout = '2s'"))
                connection.execute(text("SET LOCAL statement_timeout = '5s'"))
                connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})
                now: datetime = connection.execute(select(func.clock_timestamp())).scalar_one()
                count, latest = connection.execute(
                    select(func.count(), func.max(calls.c.reserved_at)).where(
                        calls.c.reserved_at > now - timedelta(days=1)
                    )
                ).one()
                if count >= self.policy.max_requests_per_24_hours:
                    raise ElevationDailyBudgetExceededError("24-hour elevation budget exhausted")
                if latest is not None:
                    if latest > now:
                        raise ElevationProviderUnavailableError("quota clock moved backwards")
                    delay = self.policy.minimum_interval_seconds - (now - latest).total_seconds()
                    if delay > 0:
                        connection.execute(text("SELECT pg_sleep(:delay)"), {"delay": delay})
                # Keep retention bounded without deleting active 24-hour history.
                connection.execute(
                    delete(calls).where(calls.c.reserved_at < now - timedelta(days=2))
                )
                connection.execute(
                    insert(calls).values(id=uuid4(), reserved_at=func.clock_timestamp())
                )
            # Transaction commit must succeed before the caller can invoke HTTP.
        except SQLAlchemyError:
            # SQLAlchemy errors can embed credentials/statements. Keep only a
            # safe provider error, with no attached raw exception context.
            raise ElevationProviderUnavailableError("shared elevation quota unavailable") from None
