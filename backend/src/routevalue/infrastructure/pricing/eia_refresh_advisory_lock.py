"""Cross-process exclusion for manually initiated EIA pricing refreshes.

Uses a PostgreSQL session-level advisory lock. The connection stays
checked out for the entire protected operation.

This component does not schedule refreshes or modify pricing tables.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.engine import Engine

EIA_REFRESH_LOCK_KEY = 817_203_426_001


class EiaRefreshLockUnavailableError(RuntimeError):
    """Another process holds the global EIA refresh lock."""


@contextmanager
def hold_eia_refresh_lock(engine: Engine) -> Iterator[None]:
    """Hold the global EIA refresh lock for one operation.

    The session-level lock belongs to the checked-out connection.
    A separate PostgreSQL session cannot acquire the same lock.

    The lock is released explicitly before connection cleanup.
    """

    if engine.dialect.name != "postgresql":
        raise ValueError("EIA advisory locking requires PostgreSQL")

    with engine.connect() as connection:
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": EIA_REFRESH_LOCK_KEY},
        ).scalar_one()

        if acquired is not True:
            raise EiaRefreshLockUnavailableError("another EIA pricing refresh is already running")

        try:
            yield
        finally:
            released = connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": EIA_REFRESH_LOCK_KEY},
            ).scalar_one()

            if released is not True:
                # Avoid returning a potentially unsafe connection
                # to the pool if lock ownership is unexpected.
                connection.invalidate()
                raise RuntimeError("EIA refresh advisory lock release failed")
