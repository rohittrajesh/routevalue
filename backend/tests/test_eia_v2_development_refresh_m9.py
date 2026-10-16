"""Network-free guard and workflow tests for V2 development EIA bootstrap."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Self, cast
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy.engine import Engine

from routevalue.infrastructure.persistence.config import DatabaseConfigurationError
from routevalue.infrastructure.pricing import eia_v2_development_refresh as job
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
)

DEV_URL = (
    "postgresql://neondb_owner:secret@"
    "ep-lucky-meadow-ark81i54.c-4.us-west-2.aws.neon.tech/"
    "neondb?sslmode=require&channel_binding=require"
)
DEV_AUTH = "https://ep-lucky-meadow-ark81i54.neonauth.c-4.us-west-2.aws.neon.tech/neondb/auth"


def settings(*, database_url: str = DEV_URL, auth_url: str = DEV_AUTH) -> dict[str, str]:
    return {"DATABASE_URL_UNPOOLED": database_url, "NEON_AUTH_BASE_URL": auth_url}


def test_pinned_development_target_is_accepted() -> None:
    url = job._validated_development_url(settings())
    assert url.drivername == "postgresql+psycopg"
    assert url.database == "neondb"


@pytest.mark.parametrize(
    "database_url",
    [
        (
            "postgresql://neondb_owner:secret@"
            "ep-other.c-4.us-west-2.aws.neon.tech/neondb?sslmode=require"
        ),
        DEV_URL.replace("ark81i54.c-4", "ark81i54-pooler.c-4"),
        DEV_URL.replace("/neondb?", "/production?"),
        DEV_URL.replace("neondb_owner:", "other_user:"),
        DEV_URL.replace("sslmode=require", "sslmode=disable"),
        DEV_URL.replace("neondb_owner:secret@", "neondb_owner@"),
    ],
)
def test_non_development_database_targets_are_rejected(database_url: str) -> None:
    with pytest.raises(ValueError, match="pinned, unpooled"):
        job._validated_development_url(settings(database_url=database_url))


@pytest.mark.parametrize(
    "auth_url",
    [
        "https://production.neonauth.c-4.us-west-2.aws.neon.tech/neondb/auth",
        DEV_AUTH.replace("https://", "http://"),
        DEV_AUTH.replace("/neondb/auth", "/other/auth"),
        "",
    ],
)
def test_non_development_auth_branch_is_rejected(auth_url: str) -> None:
    with pytest.raises(ValueError, match="pinned V2 Neon development Auth"):
        job._validated_development_url(settings(auth_url=auth_url))


def test_unconfigured_database_is_rejected() -> None:
    with pytest.raises(DatabaseConfigurationError, match="DATABASE_URL_UNPOOLED"):
        job._validated_development_url({"NEON_AUTH_BASE_URL": DEV_AUTH})


def mock_engine_identity(
    *,
    database: str = "neondb",
    username: str = "neondb_owner",
    revision: str = "e8a1d4c209bf",
    tables: tuple[str | None, str | None] = (
        "eia_pricing_snapshots",
        "eia_pricing_observations",
    ),
) -> Engine:
    engine = MagicMock()
    identity = MagicMock()
    identity.one.return_value = (database, username)
    alembic = MagicMock()
    alembic.scalar_one.return_value = revision
    schema = MagicMock()
    schema.one.return_value = tables
    engine.connect.return_value.__enter__.return_value.execute.side_effect = [
        identity,
        alembic,
        schema,
    ]
    return cast(Engine, engine)


def test_connected_database_identity_and_schema_are_checked() -> None:
    job._verify_database(mock_engine_identity())


@pytest.mark.parametrize(
    "database,username,revision,tables",
    [
        ("production", "neondb_owner", "e8a1d4c209bf", ("snap", "obs")),
        ("neondb", "wrong_role", "e8a1d4c209bf", ("snap", "obs")),
        ("neondb", "neondb_owner", "wrong_revision", ("snap", "obs")),
        ("neondb", "neondb_owner", "e8a1d4c209bf", ("snap", None)),
    ],
)
def test_connected_database_mismatch_is_rejected(
    database: str,
    username: str,
    revision: str,
    tables: tuple[str | None, str | None],
) -> None:
    engine = mock_engine_identity(
        database=database,
        username=username,
        revision=revision,
        tables=tables,
    )
    with pytest.raises(ValueError, match="identity or schema"):
        job._verify_database(engine)


def test_execute_without_confirmation_cannot_access_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_url(values: object) -> None:
        raise AssertionError("Database accessed without confirmation")

    monkeypatch.setattr(job, "_validated_development_url", forbidden_url)
    with pytest.raises(SystemExit) as error:
        job.main(["--execute"])
    assert error.value.code == 2


def test_missing_action_prevents_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_url(values: object) -> None:
        raise AssertionError("Database accessed without action")

    monkeypatch.setattr(job, "_validated_development_url", forbidden_url)
    with pytest.raises(SystemExit) as error:
        job.main([])
    assert error.value.code == 2


def test_read_only_check_does_not_download_or_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_engine = MagicMock()
    completed: list[str] = []

    monkeypatch.setattr(job, "_validated_development_url", lambda values: DEV_URL)
    monkeypatch.setattr(job, "create_engine", lambda *args, **kwargs: fake_engine)
    monkeypatch.setattr(job, "_verify_database", lambda engine: completed.append("verified"))
    monkeypatch.setattr(job, "_print_snapshot_status", lambda engine: completed.append("counted"))

    def forbid_refresh(**kwargs: object) -> int:
        raise AssertionError("A read-only check must not write")

    def forbid_http(**kwargs: object) -> httpx.Client:
        raise AssertionError("A read-only check must not download")

    monkeypatch.setattr(job, "run_refreshes", forbid_refresh)
    monkeypatch.setattr(httpx, "Client", forbid_http)

    assert job.main(["--check"]) == 0
    assert completed == ["verified", "counted"]
    fake_engine.dispose.assert_called_once()


def test_confirmed_execution_reuses_existing_locked_refresh_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_engine = MagicMock()
    completed: list[str] = []

    monkeypatch.setattr(job, "_validated_development_url", lambda values: DEV_URL)
    monkeypatch.setattr(job, "create_engine", lambda *args, **kwargs: fake_engine)
    monkeypatch.setattr(job, "_verify_database", lambda engine: completed.append("verified"))
    monkeypatch.setattr(job, "_print_snapshot_status", lambda engine: completed.append("counted"))

    @contextmanager
    def fake_lock(engine: Engine) -> Iterator[None]:
        completed.append("locked")
        try:
            yield
        finally:
            completed.append("unlocked")

    class FakeClient:
        def __init__(self, *, follow_redirects: bool) -> None:
            assert follow_redirects is False

        def __enter__(self) -> Self:
            completed.append("http-open")
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            completed.append("http-closed")

    def fake_refreshes(*, engine: Engine, client: object, regions: object) -> int:
        assert regions == (EIA_CALIFORNIA_REGION, EIA_US_REGION)
        completed.append("refreshed")
        return 0

    monkeypatch.setattr(job, "hold_eia_refresh_lock", fake_lock)
    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(job, "run_refreshes", fake_refreshes)

    assert job.main(["--execute", "--confirm-development-branch", "v2-development-routevalue"]) == 0
    assert completed == [
        "verified",
        "counted",
        "locked",
        "http-open",
        "refreshed",
        "http-closed",
        "unlocked",
        "counted",
    ]
    fake_engine.dispose.assert_called_once()


def test_preflight_failure_does_not_open_http_or_leak_secrets(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "database-secret-not-for-logs"

    def bad_config(values: object) -> None:
        raise ValueError(secret)

    monkeypatch.setattr(job, "_validated_development_url", bad_config)

    with caplog.at_level(logging.ERROR):
        result = job.main(
            ["--execute", "--confirm-development-branch", "v2-development-routevalue"]
        )

    assert result == 1
    assert "exception_type=ValueError" in caplog.text
    assert secret not in caplog.text
