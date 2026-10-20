# M9 batch 2 implementation and validation

Validated October 19, 2026, against V2 base commit `af77f94`, before the user's
subsequent commit/push approval. See Git history for publication state. Nothing
was merged into `main` or deployed.

## Delivered behavior

- Optional manual vehicle mass, validation, provenance, persistence and add/update/
  clear UI remain intact. New catalog saves discard upstream mass. No automatic
  manufacturer registry or weight resolution endpoint exists in this checkout.
  Historical provenance remains readable. No source files were deleted.
- Terrain acquisition fairly allocates the existing five-call trip allowance
  across candidates, reuses identical geometry/distance observations, resets trip
  guards per acquisition and preserves the shared daily guard. Models, geometry
  policies and shared honest baseline fallbacks remain in place.
- Evaluation responses and generated TypeScript now include actual energy-price
  provenance. Results show EIA versus manual pricing and original observation
  dates. Personalization changes invalidate stale and in-flight results.
- Added a configuration preflight and explicit-input terrain diagnostic CLI,
  controlled HTTP browser fixtures, desktop/mobile workflows and CI composition.
- Authentication errors retain safe actionable meaning, including the SDK's
  normalized invalid-origin error. Real local authentication requires
  `http://localhost:5173/v2` with the current development allowlist. The user
  successfully created a development account; no password or account credentials
  were changed by this work.

## Automatic gasoline pricing incident

Refreshing the two pinned development EIA snapshots was explicitly approved and
executed through the existing protected command. It yielded six observations.
Refreshing alone could not resolve the failure: on Monday October 19, EIA's latest
observation was still October 12, with the next scheduled publication October 20.

The exact seven-day rule falsely expired that currently published data. Only the
V2 EIA resolver now uses a publication-aware policy: Tuesday noon Eastern, or
Wednesday noon for recurring Monday/Tuesday federal holidays, with an absolute
ten-day ceiling. Noon includes a documented two-hour delivery allowance after
the scheduled 10 a.m. release. Dates are never rewritten. V1 and non-EIA default
freshness rules are unchanged; expired data still fails honestly, and manual
overrides retain precedence.

All three development grades resolved against the real cache after the fix:
regular 6.104, midgrade 6.401, premium 6.566 USD/gallon, observed October 12.
Authenticated browser comparisons succeeded for the user's Camry and Audi,
including the Audi's premium grade. These are validation-time values, not price
guarantees. Sources and operational instructions are in
[the live terrain guide](m9-live-terrain-guide.md).

## Executed verification

Final gates, after all code changes:

| Gate | Result |
| --- | --- |
| `uv run ruff check . --fix` | Passed |
| `uv run ruff format .` | Passed; 307 files unchanged |
| `uv run mypy .` | Passed; 307 source files |
| `uv run pytest -q` with designated local PostgreSQL URLs | **2,203 passed, 1 skipped** |
| `npm run api:generate` | Passed; OpenAPI and frontend types regenerated |
| `npm run lint` | Passed |
| `npm run format:check` | Passed |
| `npm test -- --run` | **187 passed, 33 files** |
| `npm run build` | Passed |
| `npm run test:e2e` | **10 passed**, desktop and mobile Chromium |
| Backend Docker build | Passed |
| Local container `/health`, OpenAPI and `America/New_York` timezone | Passed |
| `git diff --check` | Passed |

The full suite's sole skip is the opt-in real Google Routes test. It was executed
separately with real development configuration earlier in this batch: **1 passed**.
Backend tests retain one existing Starlette/httpx deprecation warning.

The complete suite includes the 96-case manual terrain workflow regression and
36 publication/grade combinations covering holiday and DST boundaries. Database
tests used only the existing designated disposable local PostgreSQL databases;
real Neon accounts were not used as test fixtures.

An initial final rerun was interrupted by Docker becoming unresponsive while the
Mac had only 69 MB free. A no-database run reported 2,092 passed, 100 skipped and
12 required-database setup errors; an explicit offline subset passed 2,091 tests.
After the user freed space (13 GB available), Docker was restarted without deleting
volumes. The final full database suite and container build above passed. The
environmental blockers are resolved and do not represent the final test status.
The temporary smoke-test container was removed; the existing PostgreSQL container
and its volumes were preserved.

## Live terrain evidence and limits

Real Google high-quality geometry and guarded public OpenTopoData acquisition were
tested for San Diego–Julian, Denver–Evergreen, Asheville–Waynesville,
Chicago–Evanston, Anchorage–Eagle River and Honolulu–Kailua. Both gasoline and EV
calculations used explicit diagnostic inputs: 1,800 kg, 30 MPG, 0.30 kWh/mile,
4.50 USD/gallon, 0.25 USD/kWh and 24 USD/hour. These inputs do not calibrate any
specific user's vehicle.

Terrain applied in five of six route sets after the budget fix, versus two of six
before. San Diego–Julian correctly used baseline for the complete comparison when
a sixth acquisition exceeded the five-call allowance. No route was dropped.
Applied cases had approximately 98–100% normalized coverage; this does not prove
road-grade accuracy, universal geographic coverage or future API availability.

Sanitized artifacts:
[before](validation/m9-live-terrain-before.json) and
[after](validation/m9-live-terrain-after.json).
The after artifact predates the EIA expiry fix and intentionally retains the
then-observed pricing error. The later real-cache/browser checks described above
verified its resolution. No credentials or private trip geometries are in these
artifacts.

## Changed-file scope

- Backend application: authenticated terrain orchestration, acquisition, gasoline
  quote selection/fallback, saved vehicles and manual mass update.
- Backend API: terrain composition/diagnostics, evaluation schemas/mappers/routes,
  vehicle mass/schema documentation.
- Infrastructure: EIA resolver and new release policy; `pyproject.toml`/`uv.lock`
  add explicit timezone data for minimal production containers.
- Backend tests: manual mass/catalog regression, manual terrain HTTP workflow,
  diagnostic CLI, EIA release policy and guarded browser fixture server.
- Frontend: auth panel/error classification and real SDK error regression;
  planner/result provenance/invalidation; manual mass editor and regression tests;
  OpenAPI JSON/generated types; Playwright/Vite fixtures and workflows.
- CI: install the locked backend runtime for real HTTP browser tests.
- Documentation: safe backend environment example, batch reports, operating guide
  and sanitized live artifacts. A few existing frontend files received only
  required formatter changes.

The older `/Users/roi29/Desktop/Project1/routevalue` checkout and its uncommitted
manufacturer-weight experiment were preserved untouched. Real environment files
were loaded privately from that checkout, never copied into tracked files.

## Readiness and remaining release work

This batch is implemented and independently verified. It does not establish
production launch readiness. Before enabling production live terrain, use a shared
quota limiter or explicitly review a single-instance operating model: the current
guard is process-local and restarts do not retain its daily history. Coarser
sampling may miss short hills; six distinct candidates may still fall back.

Production EIA refresh scheduling/monitoring and auth origins/session behavior
must be verified in the intended deployment. No production settings or services
were changed. Browser automation used controlled identity and upstream fixtures;
real-provider checks complement it but do not constitute an unattended real-Neon
session lifecycle test or production deployment verification. These are remaining
release gates, not tests claimed as passed.
