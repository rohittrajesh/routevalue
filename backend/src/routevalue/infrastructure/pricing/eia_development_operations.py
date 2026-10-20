"""Explicitly authorized, pinned-development EIA maintenance; never a request hook."""

import argparse
import json
import os
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    PostgresEiaPricingSnapshotRepository,
)
from routevalue.infrastructure.pricing.eia_attempt_state import AttemptState
from routevalue.infrastructure.pricing.eia_geography import EIA_CALIFORNIA_REGION, EIA_US_REGION
from routevalue.infrastructure.pricing.eia_health_check import pricing_health
from routevalue.infrastructure.pricing.eia_refresh_advisory_lock import hold_eia_refresh_lock
from routevalue.infrastructure.pricing.eia_refresh_coordinator import EiaRefreshCoordinator
from routevalue.infrastructure.pricing.eia_refresh_http_adapter import EiaWorkbookFetcher
from routevalue.infrastructure.pricing.eia_release_policy import latest_expected_eia_observation
from routevalue.infrastructure.pricing.eia_v2_development_refresh import (
    _DEVELOPMENT_BRANCH,
    _validated_development_url,
    _verify_database,
)

REGIONS = (EIA_CALIFORNIA_REGION, EIA_US_REGION)
RETRY_INTERVAL = timedelta(hours=1)


def write_private_json(path: Path, payload: dict[str, object]) -> None:
    """Replace one bounded status/state file atomically, without credential output."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".eia-")
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(payload, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_attempts(path: Path, now: datetime) -> dict[str, str]:
    if not path.exists():
        return {}
    if path.stat().st_size > 4096:
        raise ValueError("invalid operations state")
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("invalid operations state")
    attempts = value.get("attempts")
    if not isinstance(attempts, dict):
        raise TypeError("invalid operations state")
    result: dict[str, str] = {}
    for region, timestamp in attempts.items():
        if region not in {"SCA", "NUS"} or not isinstance(timestamp, str):
            raise ValueError("invalid operations state")
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None or parsed.utcoffset() is None or parsed > now:
            raise ValueError("invalid operations state clock")
        result[region] = timestamp
    return result


def run_operations(
    *,
    engine: Engine,
    state_directory: Path | None = None,
    attempt_state: AttemptState | None = None,
    client_factory: Callable[[], httpx.Client],
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Serialize monitoring/conditional refresh and throttle even unsuccessful attempts.

    Each CLI must validate its explicit target before invoking this function.
    Development uses private file state; hosted operations use shared SQL state.
    A successful refresh is not success unless source observations are usable.
    """
    with hold_eia_refresh_lock(engine):
        now = clock()
        expected = latest_expected_eia_observation(now)
        state_path = state_directory / "attempts.json" if state_directory is not None else None
        if attempt_state is not None:
            attempts = attempt_state.read(now)
        elif state_path is not None:
            attempts = read_attempts(state_path, now)
        else:
            raise ValueError("durable attempt state is required")
        repository = PostgresEiaPricingSnapshotRepository(engine=engine)
        before = pricing_health(repository, as_of=now)
        due = []
        # Read every target before constructing a downloader; DB failure cannot
        # trigger blind downloads. Future refreshes require operator review.
        for region in REGIONS:
            snapshot = repository.get_snapshot(region)
            if snapshot is not None and snapshot.refreshed_at > now:
                raise ValueError("future persisted refresh")
            needs_refresh = snapshot is None or any(
                quote.observed_at is None or quote.observed_at.date() < expected
                for quote in snapshot.quotes
            )
            if needs_refresh:
                due.append(region)
        attempted: list[str] = []
        throttled: list[str] = []
        failures: list[str] = []
        for region in due:
            region_id = region.geography.region_id
            previous = attempts.get(region_id)
            if previous is not None and now - datetime.fromisoformat(previous) < RETRY_INTERVAL:
                throttled.append(region_id)
                continue
            # Persist BEFORE any HTTP attempt. Crash/uncertain persistence wastes
            # retry opportunity conservatively; it never causes an immediate loop.
            attempts[region_id] = now.isoformat()
            if attempt_state is not None:
                attempt_state.write(attempts)
            elif state_path is not None:
                write_private_json(state_path, {"version": 1, "attempts": attempts})
            attempted.append(region_id)
            with client_factory() as client:
                result = EiaRefreshCoordinator(
                    fetch_workbook=EiaWorkbookFetcher(client=client),
                    repository=repository,
                    clock=clock,
                ).refresh(region)
            if not result.succeeded:
                failures.append(region_id)
        after = pricing_health(repository, as_of=clock())
        healthy = after["healthy"] is True and not failures
        return {
            "status": "healthy" if healthy else "degraded",
            "checked_at": clock().isoformat(),
            "expected_observation_date": expected.isoformat(),
            "attempted_regions": attempted,
            "throttled_regions": throttled,
            "failed_regions": failures,
            "before": before,
            "after": after,
        }


def operations_status(state_directory: Path, as_of: datetime) -> dict[str, object]:
    """Read bounded execution evidence; old successful output is not current health."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("status clock must be timezone aware")
    try:
        path = state_directory / "latest.json"
        if path.stat().st_size > 32768:
            raise ValueError("oversized status")
        report = json.loads(path.read_text())
        if not isinstance(report, dict) or report.get("status") not in {
            "healthy",
            "degraded",
            "unavailable",
        }:
            raise ValueError("invalid status")
        checked = datetime.fromisoformat(report["checked_at"])
        if checked.tzinfo is None or checked.utcoffset() is None or checked > as_of:
            raise ValueError("invalid status clock")
        age = as_of - checked
        return {
            "status": "stale" if age > timedelta(hours=2) else report["status"],
            "checked_at": checked.isoformat(),
        }
    except (OSError, ValueError, TypeError, KeyError):
        return {"status": "unavailable"}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--execute", action="store_true")
    action.add_argument("--status-only", action="store_true")
    parser.add_argument("--confirm-development-branch")
    parser.add_argument("--state-directory", type=Path, required=True)
    arguments = parser.parse_args(argv)
    if arguments.status_only:
        status = operations_status(arguments.state_directory, datetime.now(UTC))
        print(json.dumps(status))
        return 0 if status["status"] == "healthy" else 1
    if arguments.confirm_development_branch != _DEVELOPMENT_BRANCH:
        parser.error("requires --execute --confirm-development-branch v2-development-routevalue")
    engine = None
    try:
        url = _validated_development_url(os.environ)
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
        _verify_database(engine)
        report = run_operations(
            engine=engine,
            state_directory=arguments.state_directory,
            client_factory=lambda: httpx.Client(follow_redirects=False, timeout=20),
        )
    except Exception as error:  # noqa: BLE001 -- sanitized operational boundary
        report = {
            "status": "unavailable",
            "checked_at": datetime.now(UTC).isoformat(),
            "exception_type": type(error).__name__,
        }
    finally:
        if engine is not None:
            engine.dispose()
    try:
        write_private_json(arguments.state_directory / "latest.json", report)
    except OSError:
        print(json.dumps({"status": "status_write_failed"}))
        return 1
    print(json.dumps(report))
    return 0 if report["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
