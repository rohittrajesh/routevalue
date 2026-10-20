"""Scheduled maintenance regression: real local SQL/XLS, controlled external HTTP."""

import io
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
import xlwt  # type: ignore[import-untyped]
from sqlalchemy.engine import Engine
from test_eia_refresh_postgres_integration_m8 import (
    database_engine as database_engine,  # noqa: PLC0414 -- pytest fixture
)

from routevalue.domain.models import GasolineGrade
from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    PostgresEiaPricingSnapshotRepository,
)
from routevalue.infrastructure.pricing import eia_development_operations as operations
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_refresh_advisory_lock import (
    EiaRefreshLockUnavailableError,
    hold_eia_refresh_lock,
)
from routevalue.infrastructure.pricing.eia_release_policy import latest_expected_eia_observation

NOW = datetime(2026, 10, 14, 17, tzinfo=UTC)  # After the holiday-delayed release.


def workbook(region: EiaGasolineRegion, day: date) -> bytes:
    output = io.BytesIO()
    book = xlwt.Workbook()
    sheet = book.add_sheet("Data 1")
    sheet.write(1, 0, "Sourcekey")
    sheet.write(2, 0, "Date")
    sheet.write(
        3, 0, datetime.combine(day, datetime.min.time()), xlwt.easyxf(num_format_str="YYYY-MM-DD")
    )
    for column, grade in enumerate(GasolineGrade, start=1):
        sheet.write(1, column, region.series_for_grade(grade))
        sheet.write(2, column, grade.value)
        sheet.write(3, column, 4.125)
    book.save(output)
    return output.getvalue()


def factory(
    calls: list[str], *, failed: str | None = None, day: date = date(2026, 10, 12)
) -> Callable[[], httpx.Client]:
    def respond(request: httpx.Request) -> httpx.Response:
        region = next(r for r in operations.REGIONS if r.workbook_url == str(request.url))
        calls.append(region.geography.region_id)
        if failed in ("all", region.geography.region_id):
            return httpx.Response(503)
        return httpx.Response(200, content=workbook(region, day))

    return lambda: httpx.Client(transport=httpx.MockTransport(respond))


def test_missing_snapshots_recover_and_healthy_run_never_downloads(
    database_engine: Engine, tmp_path: Path
) -> None:
    calls: list[str] = []
    result = operations.run_operations(
        engine=database_engine,
        state_directory=tmp_path,
        client_factory=factory(calls),
        clock=lambda: NOW,
    )
    assert result["status"] == "healthy"
    assert calls == ["SCA", "NUS"]
    before = (tmp_path / "attempts.json").read_bytes()
    forbidden = Mock(side_effect=AssertionError("healthy snapshots must not download"))
    second = operations.run_operations(
        engine=database_engine,
        state_directory=tmp_path,
        client_factory=forbidden,
        clock=lambda: NOW + timedelta(minutes=1),
    )
    assert second["status"] == "healthy"
    assert second["attempted_regions"] == []
    forbidden.assert_not_called()
    assert (tmp_path / "attempts.json").read_bytes() == before


def test_partial_failure_retries_only_failed_region_after_backoff(
    database_engine: Engine, tmp_path: Path
) -> None:
    calls: list[str] = []
    first = operations.run_operations(
        engine=database_engine,
        state_directory=tmp_path,
        client_factory=factory(calls, failed="SCA"),
        clock=lambda: NOW,
    )
    assert first["status"] == "degraded"
    assert first["failed_regions"] == ["SCA"]
    repository = PostgresEiaPricingSnapshotRepository(engine=database_engine)
    national = repository.get_snapshot(EIA_US_REGION)
    calls.clear()
    second = operations.run_operations(
        engine=database_engine,
        state_directory=tmp_path,
        client_factory=factory(calls),
        clock=lambda: NOW + timedelta(minutes=30),
    )
    assert second["throttled_regions"] == ["SCA"]
    assert calls == []
    third = operations.run_operations(
        engine=database_engine,
        state_directory=tmp_path,
        client_factory=factory(calls),
        clock=lambda: NOW + timedelta(hours=1),
    )
    assert third["status"] == "healthy"
    assert calls == ["SCA"]
    assert repository.get_snapshot(EIA_US_REGION) == national


def test_failed_new_week_preserves_snapshots_then_recovers(
    database_engine: Engine, tmp_path: Path
) -> None:
    calls: list[str] = []
    old_time = NOW - timedelta(days=7)
    operations.run_operations(
        engine=database_engine,
        state_directory=tmp_path,
        client_factory=factory(calls, day=date(2026, 10, 5)),
        clock=lambda: old_time,
    )
    repository = PostgresEiaPricingSnapshotRepository(engine=database_engine)
    before = [repository.get_snapshot(region) for region in operations.REGIONS]
    failed = operations.run_operations(
        engine=database_engine,
        state_directory=tmp_path,
        client_factory=factory(calls, failed="all"),
        clock=lambda: NOW,
    )
    assert failed["status"] == "degraded"
    assert [repository.get_snapshot(region) for region in operations.REGIONS] == before
    recovered = operations.run_operations(
        engine=database_engine,
        state_directory=tmp_path,
        client_factory=factory(calls),
        clock=lambda: NOW + timedelta(hours=1),
    )
    assert recovered["status"] == "healthy"
    for region in operations.REGIONS:
        restored = repository.get_snapshot(region)
        assert restored is not None
        assert all(
            quote.observed_at is not None and quote.observed_at.date() == date(2026, 10, 12)
            for quote in restored.quotes
        )


def test_successfully_fetching_old_source_does_not_report_healthy(
    database_engine: Engine, tmp_path: Path
) -> None:
    calls: list[str] = []
    result = operations.run_operations(
        engine=database_engine,
        state_directory=tmp_path,
        client_factory=factory(calls, day=date(2026, 10, 5)),
        clock=lambda: NOW,
    )
    assert result["status"] == "degraded"
    assert result["failed_regions"] == []
    after = result["after"]
    assert isinstance(after, dict)
    assert after["healthy"] is False


def test_locked_job_never_constructs_http_or_changes_state(
    database_engine: Engine, tmp_path: Path
) -> None:
    forbidden = Mock(side_effect=AssertionError("lock must precede HTTP"))
    with hold_eia_refresh_lock(database_engine), pytest.raises(EiaRefreshLockUnavailableError):
        operations.run_operations(
            engine=database_engine,
            state_directory=tmp_path,
            client_factory=forbidden,
            clock=lambda: NOW,
        )
    forbidden.assert_not_called()
    assert not (tmp_path / "attempts.json").exists()


@pytest.mark.parametrize(
    "state",
    [
        b"not-json",
        b'{"version":2}',
        b'{"version":1,"attempts":{"SCA":"2099-01-01T00:00:00+00:00"}}',
    ],
)
def test_corrupt_or_future_state_fails_closed(
    database_engine: Engine, tmp_path: Path, state: bytes
) -> None:
    (tmp_path / "attempts.json").write_bytes(state)
    forbidden = Mock()
    with pytest.raises((ValueError, TypeError)):
        operations.run_operations(
            engine=database_engine,
            state_directory=tmp_path,
            client_factory=forbidden,
            clock=lambda: NOW,
        )
    forbidden.assert_not_called()


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        ("2026-10-20T13:59:00+00:00", "2026-10-12"),
        ("2026-10-20T14:00:00+00:00", "2026-10-19"),
        ("2026-09-08T18:00:00+00:00", "2026-08-31"),
        ("2026-09-09T14:00:00+00:00", "2026-09-07"),
        ("2026-12-01T14:59:00+00:00", "2026-11-23"),
        ("2026-12-01T15:00:00+00:00", "2026-11-30"),
    ],
)
def test_acquisition_schedule_release_holiday_and_dst(when: str, expected: str) -> None:
    assert latest_expected_eia_observation(datetime.fromisoformat(when)) == date.fromisoformat(
        expected
    )


def test_cli_requires_confirmation_before_any_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forbidden = Mock(side_effect=AssertionError("confirmation must precede access"))
    monkeypatch.setattr(operations, "_validated_development_url", forbidden)
    with pytest.raises(SystemExit):
        operations.main(["--state-directory", str(tmp_path), "--execute"])
    forbidden.assert_not_called()


def test_invalid_target_is_safe_and_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "secret-invalid-value")
    assert (
        operations.main(
            [
                "--state-directory",
                str(tmp_path),
                "--execute",
                "--confirm-development-branch",
                "v2-development-routevalue",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "secret" not in output
    assert json.loads((tmp_path / "latest.json").read_text())["status"] == "unavailable"


@pytest.mark.parametrize(
    ("age_hours", "expected"), [(0, "healthy"), (2, "healthy"), (3, "stale"), (-1, "unavailable")]
)
def test_status_rejects_stale_or_future_execution(
    tmp_path: Path, age_hours: int, expected: str
) -> None:
    operations.write_private_json(
        tmp_path / "latest.json",
        {"status": "healthy", "checked_at": (NOW - timedelta(hours=age_hours)).isoformat()},
    )
    assert operations.operations_status(tmp_path, NOW)["status"] == expected


def test_read_only_status_never_opens_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    forbidden = Mock(side_effect=AssertionError("status must not access database"))
    monkeypatch.setattr(operations, "create_engine", forbidden)
    assert operations.main(["--status-only", "--state-directory", str(tmp_path)]) == 1
    forbidden.assert_not_called()
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"
