"""Release target isolation and durable retry behavior, using disposable SQL only."""

import json
from collections.abc import Iterator, Mapping
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from test_eia_development_operations_m10 import NOW, factory
from test_eia_refresh_postgres_integration_m8 import (
    database_engine as database_engine,  # noqa: PLC0414
)

from routevalue.infrastructure.deployment.production_target import (
    load_production_target,
    validated_production_url,
)
from routevalue.infrastructure.persistence.schema import eia_refresh_attempts
from routevalue.infrastructure.pricing import eia_production_operations as production
from routevalue.infrastructure.pricing.eia_attempt_state import PostgresAttemptState
from routevalue.infrastructure.pricing.eia_development_operations import run_operations
from routevalue.infrastructure.pricing.eia_refresh_advisory_lock import (
    EiaRefreshLockUnavailableError,
    hold_eia_refresh_lock,
)
from routevalue.infrastructure.pricing.eia_v2_development_refresh import _DEVELOPMENT_DATABASE_HOST


def manifest() -> dict[str, str]:
    return {
        "branch": "v2-production-routevalue",
        "database_host": "ep-release.c-4.us-west-2.aws.neon.tech",
        "database": "neondb",
        "role": "routevalue_prod_app",
        "auth_url": "https://ep-release.neonauth.c-4.us-west-2.aws.neon.tech/neondb/auth",
        "jwks_url": "https://ep-release.neonauth.c-4.us-west-2.aws.neon.tech/neondb/auth/.well-known/jwks.json",
    }


def target_file(tmp_path: Path, **updates: str) -> Path:
    path = tmp_path / "target.json"
    path.write_text(json.dumps(manifest() | updates))
    return path


def environment() -> dict[str, str]:
    data = manifest()
    return {
        "DATABASE_URL": "postgresql://routevalue_prod_app:synthetic-secret@ep-release-pooler.c-4.us-west-2.aws.neon.tech/neondb?sslmode=require",
        "DATABASE_URL_UNPOOLED": "postgresql://routevalue_prod_app:synthetic-secret@ep-release.c-4.us-west-2.aws.neon.tech/neondb?sslmode=require",
        "NEON_AUTH_BASE_URL": data["auth_url"],
        "NEON_AUTH_JWKS_URL": data["jwks_url"],
    }


def test_reviewed_production_target_accepts_matching_pooled_and_direct_urls(tmp_path: Path) -> None:
    target = load_production_target(target_file(tmp_path))
    result = validated_production_url(environment(), target)
    assert result.host == manifest()["database_host"]


@pytest.mark.parametrize(
    "updates",
    [
        {"branch": "production"},
        {"role": "neondb_owner"},
        {"branch": "v2-development-routevalue"},
        {"database_host": _DEVELOPMENT_DATABASE_HOST},
        {"database_host": "ep-release-pooler.c-4.us-west-2.aws.neon.tech"},
        {"auth_url": "http://auth.example.test/neondb/auth"},
        {"jwks_url": "https://other.example.test/.well-known/jwks.json"},
    ],
)
def test_target_rejects_implicit_development_or_mismatched_identity(
    tmp_path: Path, updates: dict[str, str]
) -> None:
    with pytest.raises(ValueError):
        load_production_target(target_file(tmp_path, **updates))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        (
            "DATABASE_URL",
            "postgresql://routevalue_prod_app:synthetic-secret@wrong.neon.tech/neondb?sslmode=require",
        ),
        (
            "DATABASE_URL_UNPOOLED",
            "postgresql://routevalue_prod_app:synthetic-secret@ep-release-pooler.c-4.us-west-2.aws.neon.tech/neondb?sslmode=require",
        ),
        (
            "DATABASE_URL_UNPOOLED",
            "postgresql://routevalue_prod_app:synthetic-secret@ep-release.c-4.us-west-2.aws.neon.tech/neondb",
        ),
        ("NEON_AUTH_BASE_URL", "https://wrong.neonauth.neon.tech/neondb/auth"),
        ("NEON_AUTH_JWKS_URL", "https://wrong.neonauth.neon.tech/.well-known/jwks.json"),
    ],
)
def test_environment_must_match_reviewed_identity(tmp_path: Path, key: str, value: str) -> None:
    with pytest.raises(ValueError):
        validated_production_url(
            environment() | {key: value}, load_production_target(target_file(tmp_path))
        )


def test_execute_confirmation_precedes_file_database_and_http_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden = Mock(side_effect=AssertionError("must fail before DB access"))
    monkeypatch.setattr(production, "create_engine", forbidden)
    with pytest.raises(SystemExit):
        production.main(["--execute", "--target-manifest", "missing.json"])
    forbidden.assert_not_called()


@pytest.fixture
def shared_engine(database_engine: Engine) -> Iterator[Engine]:
    with database_engine.begin() as connection:
        connection.execute(delete(eia_refresh_attempts))
    try:
        yield database_engine
    finally:
        with database_engine.begin() as connection:
            connection.execute(delete(eia_refresh_attempts))


def test_failed_attempt_survives_runner_restart_and_only_due_region_recovers(
    shared_engine: Engine,
) -> None:
    calls: list[str] = []
    first = run_operations(
        engine=shared_engine,
        attempt_state=PostgresAttemptState(shared_engine),
        client_factory=factory(calls, failed="SCA"),
        clock=lambda: NOW,
    )
    assert first["status"] == "degraded"
    assert calls == ["SCA", "NUS"]
    forbidden = Mock(side_effect=AssertionError("backoff must survive new runner"))
    retry = run_operations(
        engine=shared_engine,
        attempt_state=PostgresAttemptState(shared_engine),
        client_factory=forbidden,
        clock=lambda: NOW + timedelta(minutes=20),
    )
    assert retry["throttled_regions"] == ["SCA"]
    forbidden.assert_not_called()
    recovered = run_operations(
        engine=shared_engine,
        attempt_state=PostgresAttemptState(shared_engine),
        client_factory=factory(calls),
        clock=lambda: NOW + timedelta(hours=1),
    )
    assert recovered["status"] == "healthy"
    assert calls == ["SCA", "NUS", "SCA"]
    final = run_operations(
        engine=shared_engine,
        attempt_state=PostgresAttemptState(shared_engine),
        client_factory=forbidden,
        clock=lambda: NOW + timedelta(hours=1, minutes=1),
    )
    assert final["attempted_regions"] == []
    forbidden.assert_not_called()


def test_uncertain_attempt_commit_never_reaches_http(shared_engine: Engine) -> None:
    class LostAckState(PostgresAttemptState):
        def write(self, attempts: Mapping[str, str]) -> None:
            super().write(attempts)
            raise RuntimeError("lost commit acknowledgement")

    state = LostAckState(shared_engine)
    forbidden = Mock(side_effect=AssertionError("HTTP must not run after uncertain commit"))
    with pytest.raises(RuntimeError, match="lost commit"):
        run_operations(
            engine=shared_engine, attempt_state=state, client_factory=forbidden, clock=lambda: NOW
        )
    forbidden.assert_not_called()
    assert PostgresAttemptState(shared_engine).read(NOW) == {"SCA": NOW.isoformat()}


def test_contention_and_future_shared_attempts_fail_closed(shared_engine: Engine) -> None:
    forbidden = Mock(side_effect=AssertionError("no downloader under contention"))
    with hold_eia_refresh_lock(shared_engine), pytest.raises(EiaRefreshLockUnavailableError):
        run_operations(
            engine=shared_engine,
            attempt_state=PostgresAttemptState(shared_engine),
            client_factory=forbidden,
            clock=lambda: NOW,
        )
    with shared_engine.connect() as connection:
        assert connection.execute(select(eia_refresh_attempts)).all() == []
    PostgresAttemptState(shared_engine).write({"SCA": (NOW + timedelta(hours=1)).isoformat()})
    with pytest.raises(ValueError, match="clock"):
        run_operations(
            engine=shared_engine,
            attempt_state=PostgresAttemptState(shared_engine),
            client_factory=forbidden,
            clock=lambda: NOW,
        )
    forbidden.assert_not_called()
