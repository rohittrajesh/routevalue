"""Read-only quota operations against disposable PostgreSQL; no provider traffic."""

import json
from datetime import timedelta

import pytest
from sqlalchemy import MetaData, func, insert, select
from sqlalchemy.engine import Engine
from test_shared_elevation_quota_m9 import count, gate
from test_shared_elevation_quota_m9 import (
    quota_engine as quota_engine,  # noqa: PLC0414 -- pytest fixture re-export
)

from routevalue.api import terrain_quota_health as cli
from routevalue.infrastructure.elevation import quota_health as reader
from routevalue.infrastructure.elevation.safety import PublicElevationPolicy
from routevalue.infrastructure.persistence.schema import elevation_call_reservations as calls


def test_read_only_health_reports_remaining_without_changing_history(quota_engine: Engine) -> None:
    gate(quota_engine).reserve()
    report = reader.shared_quota_health(
        quota_engine, PublicElevationPolicy(max_requests_per_trip=6)
    )
    assert report["status"] == "ready"
    assert report["active_reservations"] == 1
    assert report["remaining_requests"] == 899
    assert report["quota_writes"] == report["provider_calls"] == 0
    assert report["requests_per_trip"] == 6
    assert count(quota_engine) == 1


def test_exhaustion_is_not_reported_as_database_failure(quota_engine: Engine) -> None:
    gate(quota_engine, daily=1).reserve()
    report = reader.shared_quota_health(
        quota_engine, PublicElevationPolicy(max_requests_per_24_hours=1)
    )
    assert report["status"] == "exhausted"
    assert report["remaining_requests"] == 0
    assert count(quota_engine) == 1


def test_future_clock_state_is_not_healthy(quota_engine: Engine) -> None:
    from uuid import uuid4

    with quota_engine.begin() as connection:
        now = connection.execute(select(func.clock_timestamp())).scalar_one()
        connection.execute(insert(calls).values(id=uuid4(), reserved_at=now + timedelta(hours=1)))
    assert (
        reader.shared_quota_health(quota_engine, PublicElevationPolicy())["status"]
        == "future_reservation"
    )
    assert count(quota_engine) == 1


def test_missing_relation_is_safe_unavailable(
    quota_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        reader, "calls", calls.to_metadata(MetaData(), name="missing_health_relation")
    )
    report = reader.shared_quota_health(quota_engine, PublicElevationPolicy())
    assert report["status"] == "unavailable"
    assert "missing_health_relation" not in json.dumps(report)
    assert count(quota_engine) == 0


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({}, "disabled"),
        ({"ROUTEVALUE_TERRAIN_LIVE_ENABLED": "1"}, "process_development_only"),
        (
            {"ROUTEVALUE_TERRAIN_LIVE_ENABLED": "1", "ROUTEVALUE_TERRAIN_QUOTA_MODE": "postgres"},
            "shared",
        ),
    ],
)
def test_configuration_status(environment: dict[str, str], expected: str) -> None:
    assert cli.configuration_status(environment) == expected


def test_disabled_cli_never_opens_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ROUTEVALUE_TERRAIN_LIVE_ENABLED", "0")

    def forbidden() -> Engine:
        raise AssertionError("disabled health must not access database")

    monkeypatch.setattr(cli, "create_application_engine", forbidden)
    assert cli.main([]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "disabled"


def test_invalid_cli_configuration_is_safe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ROUTEVALUE_TERRAIN_QUOTA_MODE", "secret-must-not-appear")
    assert cli.main([]) == 2
    assert "secret-must-not-appear" not in capsys.readouterr().out
