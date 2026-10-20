"""Read-only operational health for opt-in shared terrain accounting."""

import json
import os
from collections.abc import Mapping, Sequence

from routevalue.api.terrain_v2_acquisition import configured_terrain_policy
from routevalue.infrastructure.elevation.quota_health import shared_quota_health
from routevalue.infrastructure.elevation.safety import terrain_live_enabled
from routevalue.infrastructure.persistence.config import DatabaseConfigurationError
from routevalue.infrastructure.persistence.connection import create_application_engine


def configuration_status(environment: Mapping[str, str]) -> str:
    """Require explicit live/shared mode before opening a database connection."""
    configured_terrain_policy(environment)
    enabled = terrain_live_enabled(environment)
    mode = environment.get("ROUTEVALUE_TERRAIN_QUOTA_MODE", "process")
    if mode not in ("process", "postgres"):
        raise ValueError("invalid terrain quota mode")
    if not enabled:
        return "disabled"
    return "shared" if mode == "postgres" else "process_development_only"


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    engine = None
    try:
        status = configuration_status(os.environ)
        if status != "shared":
            report: dict[str, object] = {"status": status, "provider_calls": 0, "quota_writes": 0}
        else:
            engine = create_application_engine()
            report = shared_quota_health(engine, configured_terrain_policy(os.environ))
    except (ValueError, DatabaseConfigurationError):
        report = {"status": "invalid_configuration", "provider_calls": 0, "quota_writes": 0}
        print(json.dumps(report))
        return 2
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
