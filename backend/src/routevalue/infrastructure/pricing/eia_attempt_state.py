"""Durable EIA retry accounting for ephemeral hosted runners."""

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from routevalue.infrastructure.persistence.schema import eia_refresh_attempts


class AttemptState(Protocol):
    def read(self, now: datetime) -> dict[str, str]: ...

    def write(self, attempts: Mapping[str, str]) -> None: ...


class PostgresAttemptState:
    """Used only while holding the existing global refresh advisory lock."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def read(self, now: datetime) -> dict[str, str]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(eia_refresh_attempts)).mappings().all()
        result: dict[str, str] = {}
        for row in rows:
            region = row["region_id"]
            attempted = row["attempted_at"]
            if region not in {"SCA", "NUS"} or not isinstance(attempted, datetime):
                raise ValueError("invalid shared attempt state")
            if attempted.tzinfo is None or attempted.utcoffset() is None or attempted > now:
                raise ValueError("invalid shared attempt clock")
            result[region] = attempted.isoformat()
        return result

    def write(self, attempts: Mapping[str, str]) -> None:
        with self.engine.begin() as connection:
            for region, timestamp in attempts.items():
                if region not in {"SCA", "NUS"}:
                    raise ValueError("invalid EIA attempt region")
                attempted = datetime.fromisoformat(timestamp)
                if attempted.tzinfo is None or attempted.utcoffset() is None:
                    raise ValueError("attempt clock must be timezone aware")
                statement = insert(eia_refresh_attempts).values(
                    region_id=region, attempted_at=attempted
                )
                connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=[eia_refresh_attempts.c.region_id],
                        set_={"attempted_at": statement.excluded.attempted_at},
                    )
                )
