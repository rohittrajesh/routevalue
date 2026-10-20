# M9 batch 1: optional manual curb weight

## Starting point and audit

Reviewed the four supplied V1/V2 architecture documents, the relevant application,
domain, API, vehicle-provider, persistence, terrain, pricing-composition and frontend
code, existing regression tests, migrations, OpenAPI exporter and CI configuration.
The task workspace was initially empty. Cloned `rohittrajesh/routevalue`, branch
`v2`, at `af77f94` (`feat(v2): complete M9 terrain diagnostics and vehicle mass
integration`). The checkout was clean before editing.

This revision contains no experimental manufacturer registry, automatic mass
resolution service, weight lookup endpoint, or automatic weight UI to delete.
The only mass API is the authenticated `PATCH /api/v2/vehicles/{vehicle_id}/mass`.
FuelEconomy.gov still supplies vehicle identity and gasoline/BEV efficiency.

The manufacturer/EPA mass enum values, database constraints and historical tests
remain because existing snapshots may use them. Those values represent stored
provenance; they do not provide weight acquisition. Removing them would impair
existing-record reads and contradict preservation of mass persistence/provenance.
No files or tests were deleted, and no migrations were changed or executed.

## Changes

- `application/user_saved_vehicles.py`: catalog saves explicitly discard supplied
  mass while retaining all efficiency and catalog provenance fields. Owner entry
  is the only V2 mass acquisition path, including if a future adapter returns mass.
- `application/vehicle_mass_update.py`: owner updates accept user-provided mass
  with a source reference, or clear the mass. Historical reads remain supported.
- `api/vehicle_mass.py`, `api/vehicle_schemas.py`, `domain/vehicle_mass.py`: document
  the optional manual-only policy and historical provenance compatibility.
- `api/terrain_v2_service.py`: correct stale documentation about diagnostics.
- `VehicleMassEditor.tsx`: explicitly describe optional manual weight and baseline
  behavior. Retain add/update/clear controls, units, source note and server validation.
- `V2TripResults.tsx`: remove the misleading requirement for "verified" mass;
  describe user entry and the remaining elevation prerequisites truthfully.
- Regenerate `frontend/openapi/openapi.json` and `src/api/generated/schema.ts`.
  Wire shapes remain compatible; generated descriptions now state the policy.
- Extend saved-vehicle/API/editor regressions and add
  `backend/tests/test_m9_manual_terrain_workflow.py`.
- Apply Prettier to the nine files identified by the required format check.
  `v2Resources.ts`, `v2Resources.mass.test.ts`, `PersonalizationDashboard.tsx`,
  `V2TripResults.css` and `VehicleMassEditor.css` have formatting-only changes.

## Terrain evidence and limits

The new HTTP matrix has 96 cases: gasoline/BEV × eight elevation scenarios × six
coordinate locations (San Diego, Denver, Asheville, Chicago, Anchorage, Honolulu).
Each case exercises missing mass, manual add, evaluation and clear. It uses real
acquisition, sampling, OpenTopoData response parsing, normalization, energy
evaluation and HTTP response mapping with mocked provider transport and storage.

Coordinates are real; route geometry, distances and elevations are synthetic.
These are integration tests, not recorded road routes, live coverage evidence or
model calibration. Uphill increases energy cost, downhill reduces it within the
model bounds, and flat terrain exactly preserves baseline consumption. Missing
elevation, partial coverage, quota rejection, malformed observations and untrusted
geometry force one shared baseline tier. Clearing mass restores the exact initial
response. Every response is parsed through the V2 response model and checked for
typed consumption and cost consistency.

Existing automatic EIA, manual price override, gasoline/EV, V1 compatibility,
authentication, ownership, terrain geometry and elevation safety offline tests
also passed in the complete run. Their production composition was not changed.
Live Neon OAuth, PostgreSQL persistence, Google routing, EIA workbook access and
OpenTopoData road coverage were not verified. No chargeable external API was
called, and no production configuration was changed. Live terrain remains behind
its existing explicit enablement and single-process development guards.

## Verification actually executed

| Command | Result |
| --- | --- |
| `uv sync --locked` | Passed after sandbox access approval |
| `npm ci` | Passed after sandbox network approval; existing auth peer/deprecation warnings, audit reported zero vulnerabilities |
| `uv run ruff check . --fix` | Passed; one unused import fixed |
| `uv run ruff format .` | Passed; three files formatted |
| `uv run mypy .` | Passed, 302 source files |
| `uv run pytest -q` | **Not green:** 2,049 passed, 100 skipped, 12 PostgreSQL setup errors |
| Offline rerun below | Passed: 2,048 passed, 100 skipped |
| `npm run api:generate` | Passed after sandbox cache access approval |
| `npm run lint` | Passed |
| `npm run format:check` | Initially failed on nine files; passed after formatting |
| `npm test -- --run` | Passed, 31 files / 173 tests |
| `npm run build` | Passed, TypeScript and Vite production build |
| `git diff --check` | Passed |

The backend gates were executed in the requested lint → format → mypy → pytest
order. Tests emitted the existing Starlette/httpx deprecation warning. No test
assertions were weakened to conceal a failure.

The 12 setup errors require `DATABASE_URL_UNPOOLED` and the designated isolated
local PostgreSQL database `routevalue_m8_eia_test`. The legacy database tests require
`ROUTEVALUE_TEST_DATABASE_URL` and `routevalue_m3b4`. Neither test URL is configured.
Docker is installed, but an unsandboxed `docker info` confirmed its daemon is not
running, so isolated databases could not be provisioned. The corresponding CI job
creates/migrates both databases and supplies two EIA XLS fixtures under `/tmp`.

All runnable tests were retained and executed in the full run. The separate safe
offline rerun excludes only the three modules that produced setup errors:

```sh
uv run pytest -q \
  --ignore=tests/test_eia_refresh_advisory_lock_m8.py \
  --ignore=tests/test_eia_refresh_job_lock_m8.py \
  --ignore=tests/test_eia_refresh_job_postgres_m8.py -rs
```

That exclusion also omits one passing database-independent test in those modules,
which explains the difference between 2,049 and 2,048 passing tests. Of the 100
skips, 99 require local PostgreSQL and one is the explicitly gated live Google
Routes smoke test. Playwright and container build/start tests were not run.

## Readiness

This batch is ready for review and the next M9 workflow batch. The complete backend
gate remains blocked on the local database dependencies. Deployment readiness also
requires live terrain/provider validation and authenticated browser testing.
The physical terrain model remains an approximation, and this batch makes no new
accuracy or universal coverage claim. During this batch's validation, no commits,
pushes, merges, paid-service enablement or production changes were performed.
Later batch reports supersede the environmental blockers recorded here; see Git
history for subsequent user-approved commits and pushes.
