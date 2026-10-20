"""Explicit production EIA check/refresh with reviewed target and durable retry state."""

import argparse
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import create_engine

from routevalue.infrastructure.deployment.production_target import (
    load_production_target,
    validated_production_url,
    verify_production_database,
)
from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    PostgresEiaPricingSnapshotRepository,
)
from routevalue.infrastructure.pricing.eia_attempt_state import PostgresAttemptState
from routevalue.infrastructure.pricing.eia_development_operations import run_operations
from routevalue.infrastructure.pricing.eia_health_check import pricing_health


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--execute", action="store_true")
    parser.add_argument("--target-manifest", type=Path, required=True)
    parser.add_argument("--confirm-production-branch")
    arguments = parser.parse_args(argv)
    if arguments.execute and arguments.confirm_production_branch != "v2-production-routevalue":
        parser.error("execution requires --confirm-production-branch v2-production-routevalue")
    engine = None
    try:
        target = load_production_target(arguments.target_manifest)
        url = validated_production_url(os.environ, target)
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
        verify_production_database(engine, target)
        if arguments.check:
            report = pricing_health(
                PostgresEiaPricingSnapshotRepository(engine=engine), as_of=datetime.now(UTC)
            )
            print(json.dumps(report))
            return 0 if report["healthy"] is True else 1
        result = run_operations(
            engine=engine,
            attempt_state=PostgresAttemptState(engine),
            client_factory=lambda: httpx.Client(follow_redirects=False, timeout=20),
        )
        print(json.dumps(result))
        return 0 if result["status"] == "healthy" else 1
    except Exception as error:  # noqa: BLE001 -- never print URLs, credentials or provider payloads
        print(json.dumps({"status": "unavailable", "exception_type": type(error).__name__}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
