"""Install/status/remove the local hourly EIA development LaunchAgent.

Credentials stay in the ignored env file, never in the plist. macOS user login
and an available Mac are required; this is not an always-on hosted service.
"""

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from routevalue.infrastructure.pricing.eia_development_operations import operations_status
from routevalue.infrastructure.pricing.eia_v2_development_refresh import _validated_development_url

LABEL = "com.routevalue.v2-development.eia"


def job_definition(backend: Path, uv: str) -> dict[str, object]:
    # uv splits absolute --env-file paths containing spaces in this installed
    # runtime. launchd sets WorkingDirectory; keep CLI file arguments relative.
    return {
        "Label": LABEL,
        "ProgramArguments": [
            uv,
            "run",
            "--locked",
            "--no-sync",
            "--env-file",
            ".env.v2.local",
            "python",
            "-m",
            "routevalue.infrastructure.pricing.eia_development_operations",
            "--execute",
            "--confirm-development-branch",
            "v2-development-routevalue",
            "--state-directory",
            ".runtime/eia",
        ],
        "WorkingDirectory": str(backend),
        "EnvironmentVariables": {"PYTHONPATH": str(backend / "src")},
        "RunAtLoad": True,
        "StartInterval": 3600,
        "ThrottleInterval": 60,
        "ProcessType": "Background",
        "Umask": 0o077,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": str(backend / ".runtime/eia/launcher-error.log"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "status", "uninstall"))
    parser.add_argument("--confirm-development-branch")
    arguments = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("requires macOS launchd")
    backend = Path(__file__).resolve().parents[1]
    target = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    service = f"gui/{os.getuid()}/{LABEL}"
    if arguments.action == "status":
        result = subprocess.run(
            ["/bin/launchctl", "print", service], capture_output=True, text=True, check=False
        )
        matched = re.search(r"last exit code = (\d+)", result.stdout)
        print(
            json.dumps(
                {
                    "registered": result.returncode == 0,
                    "monitor": operations_status(backend / ".runtime/eia", datetime.now(UTC)),
                    "last_exit_code": int(matched.group(1)) if matched else None,
                }
            )
        )
        healthy = (
            operations_status(backend / ".runtime/eia", datetime.now(UTC))["status"] == "healthy"
        )
        return (
            0
            if result.returncode == 0
            and matched is not None
            and matched.group(1) == "0"
            and healthy
            else 1
        )
    if arguments.confirm_development_branch != "v2-development-routevalue":
        parser.error("requires explicit pinned-development branch confirmation")
    if target.exists():
        prior = plistlib.loads(target.read_bytes())
        if prior.get("Label") != LABEL or prior.get("WorkingDirectory") != str(backend):
            raise ValueError("existing job belongs to another workspace")
    if arguments.action == "uninstall":
        subprocess.run(["/bin/launchctl", "bootout", service], check=False, capture_output=True)
        target.unlink(missing_ok=True)
        print(json.dumps({"registered": False, "operational_state_retained": True}))
        return 0
    _validated_development_url(os.environ)
    uv = shutil.which("uv")
    if uv is None or not (backend / ".env.v2.local").is_file():
        raise ValueError("local runtime/configuration missing")
    (backend / ".runtime/eia").mkdir(parents=True, exist_ok=True, mode=0o700)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(plistlib.dumps(job_definition(backend, uv)))
    target.chmod(0o600)
    subprocess.run(["/bin/launchctl", "bootout", service], check=False, capture_output=True)
    result = subprocess.run(
        ["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(json.dumps({"registered": False, "error": "launchd_bootstrap_failed"}))
        return 1
    print(
        json.dumps(
            {
                "registered": True,
                "interval_seconds": 3600,
                "run_at_load": True,
                "credentials_in_plist": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError):
        print(json.dumps({"error": "invalid_local_job_configuration"}))
        raise SystemExit(2) from None
