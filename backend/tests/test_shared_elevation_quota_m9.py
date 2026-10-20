"""Real PostgreSQL concurrency/restart tests; no external elevation traffic."""

import json
import os
import subprocess
import sys
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import MetaData, delete, func, insert, select, text
from sqlalchemy.engine import Engine

from routevalue.api import terrain_v2_acquisition as composition
from routevalue.api.terrain_v2_acquisition import (
    build_optional_terrain_acquisition_service,
    configured_terrain_policy,
)
from routevalue.application.models import ProvidedRoute, RouteGeometry, RoutePoint
from routevalue.application.terrain import ElevationSample, TerrainUnavailableReason
from routevalue.application.terrain_ports import ElevationProviderUnavailableError
from routevalue.application.terrain_sampling import TerrainSampleLocation
from routevalue.domain.models import RouteCandidate
from routevalue.infrastructure.elevation.postgres_gate import PostgresElevationCallGate
from routevalue.infrastructure.elevation.safety import (
    ElevationDailyBudgetExceededError,
    PublicElevationCallGate,
    PublicElevationPolicy,
)
from routevalue.infrastructure.persistence.connection import create_application_engine
from routevalue.infrastructure.persistence.schema import elevation_call_reservations as calls


@pytest.fixture
def quota_engine(postgres_engine: Engine) -> Iterator[Engine]:
    with postgres_engine.begin() as connection:
        connection.execute(delete(calls))
    try:
        yield postgres_engine
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(delete(calls))


def gate(engine: Engine, *, daily: int = 900) -> PostgresElevationCallGate:
    return PostgresElevationCallGate(
        engine_factory=lambda: engine,
        policy=PublicElevationPolicy(max_requests_per_trip=6, max_requests_per_24_hours=daily),
    )


def count(engine: Engine) -> int:
    with engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(calls)).scalar_one()


def test_restart_and_independent_connections_cannot_reset_daily_budget(
    quota_engine: Engine,
) -> None:
    gate(quota_engine, daily=1).reserve()
    restarted = create_application_engine(url=quota_engine.url)
    try:
        with pytest.raises(ElevationDailyBudgetExceededError):
            gate(restarted, daily=1).reserve()
        assert count(restarted) == 1
    finally:
        restarted.dispose()


def test_concurrent_gates_atomically_share_the_last_daily_slot(quota_engine: Engine) -> None:
    def reserve() -> bool:
        try:
            gate(quota_engine, daily=1).reserve()
            return True
        except ElevationDailyBudgetExceededError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: reserve(), range(2)))
    assert sorted(outcomes) == [False, True]
    assert count(quota_engine) == 1


def test_separate_python_process_observes_committed_daily_reservation(quota_engine: Engine) -> None:
    gate(quota_engine, daily=1).reserve()
    script = """
import os
from sqlalchemy.engine import make_url
from routevalue.infrastructure.persistence.connection import create_application_engine
from routevalue.infrastructure.elevation.postgres_gate import PostgresElevationCallGate
from routevalue.infrastructure.elevation.safety import PublicElevationPolicy, ElevationDailyBudgetExceededError
engine = create_application_engine(url=make_url(os.environ['QUOTA_TEST_DATABASE_URL']))
try:
    gate = PostgresElevationCallGate(engine_factory=lambda: engine, policy=PublicElevationPolicy(max_requests_per_24_hours=1))
    try:
        gate.reserve()
    except ElevationDailyBudgetExceededError:
        print('denied')
    else:
        raise AssertionError('A different process reset the budget')
finally:
    engine.dispose()
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            "QUOTA_TEST_DATABASE_URL": quota_engine.url.render_as_string(hide_password=False),
        },
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "denied"
    assert count(quota_engine) == 1


def test_lock_contention_fails_closed_without_new_reservation(quota_engine: Engine) -> None:
    from routevalue.infrastructure.elevation.postgres_gate import _LOCK_KEY

    with quota_engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})
        with pytest.raises(
            ElevationProviderUnavailableError, match="shared elevation quota unavailable"
        ):
            gate(quota_engine).reserve()
    assert count(quota_engine) == 0


def test_separate_gates_enforce_database_time_spacing(quota_engine: Engine) -> None:
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: gate(quota_engine).reserve(), range(2)))
    with quota_engine.connect() as connection:
        times = (
            connection.execute(select(calls.c.reserved_at).order_by(calls.c.reserved_at))
            .scalars()
            .all()
        )
    assert (times[1] - times[0]).total_seconds() >= 1.1


def test_rolling_window_and_retention_use_db_clock(quota_engine: Engine) -> None:
    with quota_engine.begin() as connection:
        now: datetime = connection.execute(select(func.clock_timestamp())).scalar_one()
        connection.execute(
            insert(calls),
            [
                {"id": uuid4(), "reserved_at": now - timedelta(hours=25)},
                {"id": uuid4(), "reserved_at": now - timedelta(days=3)},
            ],
        )
    gate(quota_engine, daily=1).reserve()
    assert count(quota_engine) == 2  # 25-hour event retained but outside active budget.
    with pytest.raises(ElevationDailyBudgetExceededError):
        gate(quota_engine, daily=1).reserve()


def test_future_database_reservation_fails_closed(quota_engine: Engine) -> None:
    with quota_engine.begin() as connection:
        connection.execute(
            insert(calls).values(
                id=uuid4(), reserved_at=func.clock_timestamp() + text("interval '1 hour'")
            )
        )
    with pytest.raises(ElevationProviderUnavailableError, match="clock"):
        gate(quota_engine).reserve()
    assert count(quota_engine) == 1


class FailingProvider:
    requests = 0

    def get_elevations(
        self, locations: Sequence[TerrainSampleLocation]
    ) -> tuple[ElevationSample, ...]:
        self.requests += 1
        raise ElevationProviderUnavailableError("upstream outage")


def test_failed_upstream_attempt_remains_charged_after_new_trip(quota_engine: Engine) -> None:
    provider = FailingProvider()
    locations = (
        TerrainSampleLocation(point=RoutePoint(latitude=32, longitude=-117), distance_meters=0),
    )
    with pytest.raises(ElevationProviderUnavailableError):
        gate(quota_engine, daily=1).new_trip(provider).get_elevations(locations)
    with pytest.raises(ElevationDailyBudgetExceededError):
        gate(quota_engine, daily=1).new_trip(provider).get_elevations(locations)
    assert provider.requests == 1
    assert count(quota_engine) == 1


@pytest.mark.parametrize("failure", ["missing_table", "missing_database"])
def test_quota_outage_never_calls_provider_and_yields_honest_fallback(
    quota_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    monkeypatch.setenv("ROUTEVALUE_TERRAIN_LIVE_ENABLED", "1")
    monkeypatch.setenv("ROUTEVALUE_TERRAIN_QUOTA_MODE", "postgres")
    monkeypatch.delenv("ROUTEVALUE_TERRAIN_SINGLE_PROCESS_DEV", raising=False)
    # Exercise real DB errors without deleting tables or changing schema.
    bad_engine = create_application_engine(
        url=quota_engine.url.set(database="missing_quota_test_database")
        if failure == "missing_database"
        else quota_engine.url
    )
    if failure == "missing_table":
        from routevalue.infrastructure.elevation import postgres_gate

        monkeypatch.setattr(
            postgres_gate, "calls", calls.to_metadata(MetaData(), name="missing_quota_relation")
        )
    route = ProvidedRoute(
        route=RouteCandidate(distance_meters=1000, duration_seconds=120, toll_cost=Decimal(0)),
        geometry=RouteGeometry(
            points=(
                RoutePoint(latitude=32, longitude=-117),
                RoutePoint(latitude=32.01, longitude=-117),
            )
        ),
    )

    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("No external call is permitted without a committed reservation")

    try:
        with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
            service = build_optional_terrain_acquisition_service(
                client=client, engine_factory=lambda: bad_engine
            )
            assert service is not None
            results = service.acquire_routes((route,))
        assert results[0].unavailable_reason is TerrainUnavailableReason.PROVIDER_UNAVAILABLE
        assert count(quota_engine) == 0
    finally:
        bad_engine.dispose()


@pytest.mark.parametrize("value", ["0", "7", "900", "true", "", " 6", "6.0"])
def test_live_trip_allowance_rejects_invalid_settings(value: str) -> None:
    with pytest.raises(ValueError, match="exactly"):
        configured_terrain_policy({"ROUTEVALUE_TERRAIN_REQUESTS_PER_TRIP": value})


def test_live_trip_allowance_increase_does_not_raise_daily_or_rate_limits() -> None:
    policy = configured_terrain_policy({})
    assert policy.max_requests_per_trip == 6
    assert policy.max_requests_per_24_hours == 900
    assert policy.minimum_interval_seconds == 1.1
    assert (
        configured_terrain_policy(
            {"ROUTEVALUE_TERRAIN_REQUESTS_PER_TRIP": "5"}
        ).max_requests_per_trip
        == 5
    )


@pytest.mark.parametrize("budget", [5, 6])
def test_six_distinct_candidates_retained_and_sixth_call_can_complete(
    budget: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]

    def advance(seconds: float) -> None:
        clock[0] += seconds

    policy = PublicElevationPolicy(max_requests_per_trip=budget)
    shared = PublicElevationCallGate(
        enabled=True, policy=policy, clock=lambda: clock[0], sleeper=advance
    )
    monkeypatch.setenv("ROUTEVALUE_TERRAIN_LIVE_ENABLED", "1")
    monkeypatch.setenv("ROUTEVALUE_TERRAIN_SINGLE_PROCESS_DEV", "1")
    monkeypatch.setenv("ROUTEVALUE_TERRAIN_QUOTA_MODE", "process")
    monkeypatch.setenv("ROUTEVALUE_TERRAIN_REQUESTS_PER_TRIP", str(budget))
    monkeypatch.setattr(composition, "_shared_elevation_gate", lambda policy: shared)
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        pairs = json.loads(request.content)["locations"].split("|")
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "results": [
                    {
                        "location": {
                            "lat": float(pair.split(",")[0]),
                            "lng": float(pair.split(",")[1]),
                        },
                        "elevation": 100,
                        "dataset": "ned10m",
                    }
                    for pair in pairs
                ],
            },
        )

    routes = tuple(
        ProvidedRoute(
            route=RouteCandidate(
                distance_meters=1112, duration_seconds=120 + index, toll_cost=Decimal(0)
            ),
            geometry=RouteGeometry(
                points=(
                    RoutePoint(latitude=32, longitude=-117 + index * 0.01),
                    RoutePoint(latitude=32.01, longitude=-117 + index * 0.01),
                )
            ),
        )
        for index in range(6)
    )
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        service = build_optional_terrain_acquisition_service(client=client)
        assert service is not None
        results = service.acquire_routes(routes)
    assert len(results) == 6
    assert [result.route_index for result in results] == list(range(6))
    assert len(requests) == budget
    assert sum(result.profile is not None for result in results) == budget
    assert results[-1].unavailable_reason is (
        TerrainUnavailableReason.REQUEST_BUDGET_EXCEEDED if budget == 5 else None
    )


def test_commit_acknowledgement_failure_never_calls_provider_and_keeps_reservation(
    quota_engine: Engine,
) -> None:
    """A lost commit acknowledgement must waste quota rather than allow free HTTP."""
    from contextlib import contextmanager
    from unittest.mock import Mock

    from sqlalchemy.engine import Connection
    from sqlalchemy.exc import OperationalError

    @contextmanager
    def uncertain_commit() -> Iterator[Connection]:
        with quota_engine.begin() as connection:
            yield connection
        # Model the transaction committed, but the client never received its ACK.
        raise OperationalError("commit acknowledgement lost", None, RuntimeError("synthetic"))

    uncertain = Mock(spec=Engine)
    uncertain.begin.side_effect = uncertain_commit
    provider = FailingProvider()
    locations = (
        TerrainSampleLocation(point=RoutePoint(latitude=32, longitude=-117), distance_meters=0),
    )
    protected = PostgresElevationCallGate(
        engine_factory=lambda: uncertain,
        policy=PublicElevationPolicy(),
    ).new_trip(provider)
    with pytest.raises(
        ElevationProviderUnavailableError, match="shared elevation quota unavailable"
    ):
        protected.get_elevations(locations)
    assert provider.requests == 0
    assert count(quota_engine) == 1
