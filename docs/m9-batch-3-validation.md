# M9 batch 3: terrain capacity and operational hardening

Completed October 19, 2026 (America/Los_Angeles), before the user's subsequent
commit/push approval for `v2`. See Git history for publication state. Earlier
changes and the original Desktop checkout were preserved. No files were deleted,
no paid service enabled, no production configuration changed and nothing merged
into `main` or deployed.

## Delivered

- Live terrain defaults to six calls/trip, configurable to exactly five or six.
  The 900-call rolling daily ceiling, 1.1-second interval and 100-point batches
  remain unchanged. Generic low-level policy still defaults to five for existing
  consumers; live composition explicitly selects six. No provider charge was added.
- Optional PostgreSQL quota mode coordinates workers and survives restart.
  Reservations commit before HTTP, failed attempts remain counted, and database
  time/advisory locking serialize the shared allowance. Missing migrations,
  database errors and lock contention prevent external calls and yield baseline.
  There is no fallback to an unmetered process gate or HTTP retry.
- Additive migration `f2b7c39a106d` creates a timestamp/UUID reservation table and
  index. No profile, vehicle, preference, EIA or Auth data is changed. Automatic
  cleanup retains active 24-hour history and removes quota events older than
  48 hours. Schema downgrade refuses to drop active accounting history.
- Read-only EIA health command checks both supported regions and every gasoline
  grade using the real resolver's publication deadline. Missing regional data,
  stale/future observations, future refresh time and storage failure are unhealthy.
  Output contains safe statuses/timestamps; it cannot change cache freshness.
- Updated CI/current-schema assertions and preserved protected EIA refresh access
  on both the original EIA revision and the new additive revision.
- Added an operations runbook covering enablement, rollback, retention, quota
  scope, monitoring, source publication and current provider cost tradeoffs.

## Verification actually executed

| Check | Final result |
| --- | --- |
| `uv run ruff check . --fix` | Passed |
| `uv run ruff format .` | Passed; 312 files unchanged |
| `uv run mypy .` | Passed; 312 source files |
| `uv run pytest -q`, both designated local databases configured | **2,231 passed, 1 skipped** |
| Additive migration on both disposable local databases | Passed |
| `uv run alembic check`, both local databases | Passed; no new operations |
| `npm run api:generate` | Passed; generated contract remains aligned |
| `npm run lint` | Passed |
| `npm run format:check` | Passed |
| `npm test -- --run` | **187 passed, 33 files** |
| `npm run build` | Passed |
| `npm run test:e2e` | **10 passed**, V1 and desktop/mobile V2 |
| Docker image build; local container health/default preflight | Passed |
| Restarted development backend health/configuration preflight | Passed; live enabled, process mode, six calls |
| Read-only real development EIA monitor | Passed; both regions/all grades healthy |
| `git diff --check` | Passed |

The one suite skip is the opt-in live Google smoke test. It was not rerun as that
specific pytest test in this batch; real Google/OpenTopoData acquisition was tested
separately below. The existing Starlette/httpx warning remains. An initial full run
found the new subprocess test lacked its source import path: fixed with explicit
`PYTHONPATH`, then the complete suite passed. No assertions were weakened.

New coverage includes competing independent gates for the last daily slot,
cross-connection spacing, a separate Python process observing committed history,
rolling expiry/retention, failed upstream accounting, future database time,
advisory-lock timeout, missing database/relation fallback, malformed configuration,
and six distinct retained candidates under five-call versus six-call policies.

## Live evidence

The existing private development environment files were loaded without copying or
printing credentials. No remote database writes were performed in this batch.

A fresh Google `HIGH_QUALITY` San Diego–Julian request returned **three candidates**.
The new policy allocated two public elevation batches per candidate and committed
**six quota reservations in the disposable local database**. Every acquisition
completed, normalized coverage was 1 for all three and terrain applied to both
gasoline and EV models. The diagnostic used explicit 1,800 kg/30 MPG/0.30 kWh per
mile, 4.50 USD/gallon, 0.25 USD/kWh and 24 USD/hour inputs; these do not calibrate
any real vehicle. All estimates differed from their exact baseline as expected.

Sanitized evidence: [live six-call quota](validation/m9-live-six-call-quota.json).
Google returned a different candidate set from the earlier six-candidate run, so
this is not claimed as an identical before/after route comparison. Six distinct
candidate capacity was separately proven with controlled provider responses.

Real development Neon remained at `e8a1d4c209bf`. JWKS returned HTTP 200 and the
real EIA regional quote resolved. The new monitor reported both California and
national snapshots healthy for all three grades, observed October 12. Those are
validation-time results; the next source publication/expiry still requires normal
refresh operations. No observation timestamp was advanced to fabricate freshness.

The local app backend was restarted and restored on port 8000 with the original
private configuration. Its preflight confirmed six-call process mode. Frontend
and account state were left intact. The temporary smoke container was removed;
the existing PostgreSQL service/volumes were preserved.

## File scope

New files:

- `backend/migrations/versions/f2b7c39a106d_elevation_call_reservations.py`
- `backend/src/routevalue/infrastructure/elevation/postgres_gate.py`
- `backend/src/routevalue/infrastructure/pricing/eia_health_check.py`
- `backend/tests/test_shared_elevation_quota_m9.py`
- `backend/tests/test_eia_health_check_m9.py`
- This report, `m9-deployment-operations.md` and the sanitized live artifact.

Updated: terrain acquisition composition, V2 dependency wiring, diagnostics,
elevation policy/gate protocol, persistence metadata, EIA CLI schema guards,
backend `.env.example`, migration/schema/test fixtures, CI head assertions and the
live terrain guide. No frontend implementation change was needed in this batch.

## Deployment boundaries and remaining work

Shared quota mode is implemented and tested, including real upstream calls with
local PostgreSQL, but has not been activated in Neon or production. Applying the
additive migration and choosing a deployment-wide shared database remain explicit
enablement steps. All workers sharing an upstream IP must use the same gate and
database; unrelated consumers of that IP are outside this application's control.
Quota failures/lock contention may conservatively fall back before 900 calls.

The six-call public-provider increase adds zero elevation-provider fees, within
[published OpenTopoData limits](https://www.opentopodata.org/). It does not cap
existing Google Routes/Maps/Places or database usage bills. The operations guide
records Google's current Elevation alternative and why its estimated $10 usage
cost is not an account-level hard spending cap. No billing configuration changed.

Production EIA refresh scheduling and monitoring provisioning, real deployed Neon
auth/session checks, and final deployment/release approval remain outstanding.
No scheduler was registered. The monitor was validated on existing data, not a
subsequent weekly release. Terrain evidence does not establish universal coverage,
road-grade accuracy or an SLA. This batch is verified; production launch readiness
is not asserted.
