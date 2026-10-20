# M10 batch 3: shared terrain accounting and operational acceptance

Based on `90d904f` on `v2`. This batch activates shared PostgreSQL quota accounting
for the local V2 backend with the pinned Neon development branch. Production V1,
`main`, hosted configuration and authentication policies were not modified.

## Activation and invariants

The existing quota migration was already present at schema head `a19d6e2c740b`.
Before activation, the pinned database/Auth guard, application-versus-migration
URL identity, database role/schema and quota SELECT/INSERT/DELETE privileges were
verified privately. `alembic check` subsequently found no new upgrade operations.
No migration, schema deletion, quota truncation or history reset was performed.

The active configuration is now the ignored private file
`backend/.env.v2.local` in this project workspace. It reuses the existing pinned
development configuration and sets only the terrain flags:

```dotenv
ROUTEVALUE_TERRAIN_LIVE_ENABLED=1
ROUTEVALUE_TERRAIN_QUOTA_MODE=postgres
ROUTEVALUE_TERRAIN_REQUESTS_PER_TRIP=6
ROUTEVALUE_TERRAIN_SINGLE_PROCESS_DEV=0
```

The local backend was restarted with that file, then restarted again after the
live reservations to confirm persistence. The older Desktop checkout/environment
and its local changes remain untouched. The private file is mode 0600, ignored by
Git and absent from commits/container context. Start future local backend sessions
from `backend/` with `uv run --env-file .env.v2.local ...`.

Limits remain six calls/trip, 900 reservations per rolling 24 hours, 100 sampled
locations per provider batch and at least 1.1 seconds between committed reservation
timestamps. Failed attempts count. There are no implicit elevation retries, paid
provider activation or increases to daily/rate ceilings. Every worker sharing this
upstream IP must use the same database/mode; unrelated consumers are outside this
ledger. This batch does not claim the user’s entire Google billing account has an
enforced monetary cap or that SQL health checks prove chargeable API entitlement.

The previous backend’s session logs contained no trip-evaluation requests since
its recorded batch-2 startup. No process-local history was imported: the initial
shared ledger was empty. The evidence proves accounting from activation forward,
not reconstruction of all provider traffic in the preceding 24 hours. Retain that
transition limitation when interpreting the first shared rolling window. Do not
switch back to process mode or delete history to recover allowance.

## Operational diagnostic

New `routevalue.api.terrain_quota_health` composes the existing policy and a new
infrastructure read-only ledger reader. It uses a READ ONLY transaction and bounded
SQL statements. It never reserves, prunes history, calls Google/OpenTopoData or
publishes credentials, hosts or account identifiers. API → infrastructure
dependency direction is preserved; the infrastructure reader does not import API
composition. No new HTTP endpoint or public OpenAPI change is introduced.

Run from `backend/`:

```sh
PYTHONPATH=src uv run --env-file .env.v2.local \
  python -m routevalue.api.terrain_quota_health
```

Exit 0: ready shared snapshot. Exit 1: disabled/process-only/exhausted/unavailable,
permission-denied or future-clock state. Exit 2: invalid configuration. Existing
engine connection/pool timeouts remain separate from the five-second SQL statement
timeout. A read-only “ready” snapshot does not reserve capacity or prevent another
worker from using the remaining allowance immediately afterward. The command is
available for future monitoring; no scheduler was installed by this batch.

## Live and failure evidence

[Sanitized evidence](validation/m10-live-shared-terrain.json) contains public route
labels, candidate/geometry counts, typed energy/model/status results, limits,
ledger timestamps/counts and verification booleans. It contains no raw polylines,
credentials, tokens, account IDs, private hosts or personal trip locations.

| Public comparison | Google candidate count | Gasoline terrain | EV terrain |
| --- | --- | --- | --- |
| San Diego–Julian, CA | 2 | Applied to both | Applied to both |
| Denver–Idaho Springs, CO | 2 | Applied to both | Applied to both |
| Asheville–Cherokee, NC | 3 | Applied to all three | Applied to all three |

- Actual Google `HIGH_QUALITY` route acquisition made **6 requests**. OpenTopoData
  made **18 attempts**, bounded to six per comparison. Both energy models reused
  the same acquisition within each comparison. Every applied cost differed from
  its corresponding exact baseline cost; response terrain statuses reported
  applied with no fallback reasons for these sampled routes.
- Inputs were explicit illustrative diagnostic mass 1800 kg, gasoline efficiency
  30 MPG, EV efficiency 0.30 kWh/mile, gasoline price 4.50, electricity price 0.25
  and value of time 24. They were never inferred from a manufacturer or written to
  a saved vehicle/profile. These are model integration checks, not vehicle-specific
  calibration claims. Automatic EIA pricing remains present and regression-tested;
  this controlled terrain comparison used manual diagnostic prices.
- The ledger rose from **0 to 18**, exactly matching elevation attempts. After an
  actual backend restart it remained **18**, with **882 remaining** at that check.
  Minimum recorded inter-reservation spacing was **1.250674 seconds**. This is a
  database reservation measurement, not a multi-worker network timing guarantee.
- A fresh Python process, followed by two concurrent independent Python workers,
  observed committed history. Their denial probe used a deliberately conservative
  one-call policy against the existing 18 rows; it added no reservations or HTTP
  requests. Atomic competition for the last slot and restart sharing are also
  covered by actual local PostgreSQL tests.
- Holding the development quota advisory lock made acquisition fail closed:
  **zero HTTP calls, zero new reservations**, truthful provider-unavailable/shared
  baseline status for gasoline and EV. The lock was transaction-scoped and released
  normally. No table/role/production failure was injected.
- Missing-mass offline diagnostics produced exact baseline costs for both models.
  Existing manual-mass and shared-tier suites cover missing mass with acquisition,
  incomplete profiles and quota/provider failures through the HTTP/application path.
- Aggregate fingerprints before/after confirmed unchanged users, auth identities,
  saved vehicles, preferences, EIA snapshots and EIA observations. Only the quota
  ledger received the counted operational reservations. No EIA refresh occurred.

Complete raster coverage on these seven candidates does not establish universal
US coverage, measured road grades, physical accuracy or production readiness.
Public-provider/IP limits, network outages and database contention can still
produce baseline fallback. A provider request already sent cannot be undone; quota
reservation always precedes delegation.

## Regression and final gates

New health tests cover ready/remaining, exhausted, future-clock and missing-relation
states, disabled operation without DB access and safe invalid configuration.
A new lost-commit-acknowledgement regression models a committed reservation whose
acknowledgement fails: the provider is never invoked and the row stays charged.
Existing shared-quota tests cover missing DB/table, contention, concurrent last
slot, spacing, retention, process restart and failed upstream calls staying charged.

| Executed check | Final result |
| --- | --- |
| `uv run ruff check . --fix` | Passed |
| `uv run ruff format .` | Passed |
| `uv run mypy .` | Passed, 319 source files |
| `uv run pytest -q`, designated local databases | **2,270 passed, 1 skipped** |
| Pinned development `alembic check` | Passed; no upgrade operations |
| `npm run api:generate` / `npm run api:check` | Passed; no contract/type diff |
| `npm run lint` | Passed |
| `npm run format:check` | Passed |
| `npm test -- --run` | **205 passed, 34 files** |
| `npm run build` | Passed |
| `npm run test:e2e` | **20 passed**, desktop/mobile and V1 journeys |
| Backend Docker image build | Passed |

The single backend skip is the opt-in Google Routes smoke test. It was not silently
counted as passed: the separate explicitly executed public-route harness above
made real Google/OpenTopoData calls. Existing Starlette/httpx and browser color
warnings remain. No frontend implementation changed in this batch.

New files: API quota-health CLI, infrastructure read-only quota reader, PostgreSQL
health regression suite, this validation report and sanitized live evidence.
Updated: commit-failure regression, operations/local terrain guides, architecture
record and README. No files were deleted. Private configuration is an intentional
ignored local artifact; API generation produces no tracked diff.

## Next work

M10 batch 3 is complete for the authorized local/pinned-development environment.
Next is batch 4: EIA refresh/monitor operations, scheduling and failure recovery,
then final integrated release acceptance. No hosted V2 staging currently exists.
Batch 2’s password-recovery UI/email-delivery and hosted-authentication release
checks remain open; they are not closed by successful terrain validation.
M11 still requires approved production configuration/migrations, exact-release
smokes, rollback, merge/deployment and tagging. No paid service was activated.
