"""Export RouteValue's FastAPI OpenAPI schema deterministically."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from routevalue.main import app


def main() -> None:
    """Write the current FastAPI OpenAPI schema to the requested path."""

    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/export_openapi.py <output-path>")

    output_path = Path(sys.argv[1]).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    schema = app.openapi()

    output_path.write_text(
        json.dumps(
            schema,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
