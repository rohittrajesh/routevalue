# M10 batch 1: acceptance and preference consistency

Scope: the first integration/hardening batch, based on `0ba16b1` on `v2`.
This audits the supplied V2 vision/M0 freeze, reconciled architecture, M9 closure,
implementation, tests, persistence/migrations, generated API workflow and CI.
It does not close M10 or certify a production release.

## Acceptance matrix

Paths below are repository-relative. “Covered” means implementation review plus
executed automated coverage, with external dependencies controlled unless stated.
It does not mean deployed/staging or universal provider validation.

| Requirement | Implementation | Evidence | Batch 1 disposition |
| --- | --- | --- | --- |
| Authenticated identity and ownership | API identity dependency, internal UserId, owner-scoped saved vehicles and preferences, composite owned-default FK | `test_api_authentication.py`, `test_authentication_hardening.py`, `test_api_v2_authorization_hardening.py`, authenticated PostgreSQL suites | Covered; real deployed session lifecycle remains batch 2 |
| Explicit defaults, no invented economic preferences | `application/preferences.py`, `profile_resolution.py` | `test_user_preferences.py`, `test_profile_resolution.py`, `test_m9_energy_preferences.py` | Covered: unset differs from zero; missing configuration returns structured errors |
| Default versus explicit vehicle | Owner-scoped profile resolution; explicit selection takes precedence | `test_profile_resolution.py` explicit/default/missing/foreign cases | Covered; frontend's visible initial selection is sent explicitly and does not silently persist a default |
| Independent preference PATCHes | Typed sparse application port and PostgreSQL field updates | **`test_m10_preference_consistency.py`** | Fixed lost updates on both first insert and existing rows |
| Default deletion and concurrent changes | Transactional owner-row locking shared by preference writes and vehicle deletion; ownership rechecked within write transaction | New interleaving/deletion regressions; existing authenticated vehicle PostgreSQL tests | Fixed stale-default resurrection and validation/delete race; unavailable defaults return 404 with all other submitted changes rolled back |
| Preference persistence and clear semantics | Nullable Decimal rate and complete coordinate/name market bundle | `test_m9_energy_preferences.py`, new no-op/null regression | Covered; omitted fields preserve state; explicit null clears only that setting |
| EV price precedence/provenance | Explicit electricity input, otherwise saved user rate | `test_m9_energy_preferences.py`, `test_profile_trip_evaluation_electric.py`, V2 browser journeys | Covered, including zero, clear, reload, override without storage mutation and wrong energy type rejection |
| Automatic gasoline pricing and manual override | Persisted EIA snapshots; saved market coordinates, otherwise origin; manual price bypass | `test_authenticated_automatic_gasoline_m8.py`, `test_m9_energy_preferences.py`, pricing temporal/fallback tests | Covered; automatic pricing retained; unsupported/stale data fails honestly |
| Gasoline/EV energy and exact costs | Separate typed consumption and price quotes; shared decision engine | Gasoline/electric energy and evaluation suites, `test_gasoline_energy_migration.py` | Covered; Decimal money and original decision/tie rules preserved |
| Manual mass lifecycle | Owned manual-only mass/provenance API and settings | `test_m9_manual_terrain_workflow.py`, PostgreSQL mass tests, V2 browser journeys | Covered; no automatic weight lookup/registry restored; efficiency lookup preserved |
| Terrain applicability and response honesty | Google Routes geometry policy; guarded OpenTopoData acquisition; shared comparison tier | `test_api_terrain_status_m9.py`, `test_terrain_trip_fairness_regression_m7.py`, terrain gasoline/EV suites | Covered with fixtures; no new live geographic coverage claim |
| Provider failures, caching and quotas | Bounded acquisition, repeat-shape reuse, persisted EIA reads, optional shared PostgreSQL quota | Acquisition/fallback suites, `test_terrain_diagnostics_m9.py`, `test_shared_elevation_quota_m9.py` | Covered offline/local SQL; shared-mode activation and operational observation remain later M10 work |
| V1 cost, recommendation and HTTP/UI compatibility | Existing unversioned API/UI and baseline behavior | `test_v1_gasoline_compatibility.py`, `test_gasoline_energy_migration.py`, M5 regression suites, V1 Playwright journeys | Covered; no V1 production/configuration changes |
| Public schema and strict clients | Deterministic FastAPI export → OpenAPI → TypeScript, CI drift check | API generation, schema/security tests, frontend typechecked build | Regenerated with **no public contract/type diff** |
| Desktop/mobile integrated workflow | Authenticated planner, garage/settings, retained locations and honest recovery | 14 Playwright journeys using controlled test-only identity/upstream/storage adapters | Covered; these fixtures are not real Neon authentication or staging evidence |
| Original provider scope | `v2-architecture-decisions.md` | Documentation and composition review | OpenTopoData/EIA/email-password implemented; Google Elevation, Places station-price aggregation and Google OAuth explicitly deferred |

## Implementation and concurrency contract

The API previously read a full preference snapshot, merged submitted fields and
saved every field. A second request could change an omitted field between those
operations; the first request then overwrote that change. It could also restore a
default vehicle deleted after the snapshot was read, causing a foreign-key failure.

The API now maps only explicitly submitted fields into `UserPreferencesPatch`.
Application setters use the same sparse repository operation. PostgreSQL upserts
update only those columns, with market name/coordinates written as one bundle.
All preference writes and default-clearing vehicle deletions acquire the same
user-row lock before touching preference/vehicle state. This also covers users
without a preference row yet. Ownership validation inside that transaction closes
the gap after the API's preliminary ownership check.

Unrelated fields survive overlapping writes. Conflicting writes to the **same**
field use the last successful transaction's value; this is not optimistic version
conflict detection. Responses represent the state at that transaction, not a
subscription to subsequent changes in another tab. Repeated equivalent updates to
existing rows preserve `updated_at`. Complete-state `save_preferences` remains an
explicit replacement operation for existing callers/seeding; HTTP PATCH and
single-field application setters no longer use it.

No migration is needed. Schema remains `a19d6e2c740b`. The owned-default composite
foreign key remains the database backstop. Test repositories/browser fixtures were
updated to implement the typed sparse port; real concurrency assertions use actual
PostgreSQL transactions, not those in-memory adapters.

## Test environment and debugging

The initial full run could not connect to PostgreSQL because Docker Desktop was
stopped. Docker and the existing disposable test container were restored. The
next run identified missing `/tmp` public EIA workbook fixtures; those were
redownloaded from the same EIA URLs used by CI. No remote database was refreshed.

The downloaded observations then revealed a historical test-clock bug: real XLS
integration tests used October 13, 2026 as their refresh timestamp even for newer
workbooks. They now inject a per-test frozen actual UTC retrieval time. Assertions
still compare source dates, exact prices, snapshots and refresh timestamps;
production snapshot/future-date validation was not weakened. The controlled
future-observation, malformed-content and failed-refresh tests remain in the full
suite. Initial failing runs are superseded only by the successful final run below.

## Remaining M10 and release work

1. Real Neon session lifecycle and staging acceptance: sign-in/out, expiration,
   registration/recovery policy, and persistence across actual authenticated sessions.
2. Guarded development/staging activation of shared PostgreSQL terrain accounting,
   with worker/restart, fail-closed and bounded live provider evidence.
3. EIA refresh/monitor scheduling and operational observation/recovery. Successful
   local snapshot tests do not prove an unattended deployed refresh job exists.
4. Final integrated release-candidate checks and confirmation of supported provider
   scope before M11. Original Google provider proposals are not silently certified.

M11 still owns approved production migrations/configuration, exact-commit live
smoke tests, rollback, merge/deployment and release tagging. No paid service,
production configuration, remote migration or `main` merge was performed here.

## Final executed checks

| Gate | Final result |
| --- | --- |
| `uv run ruff check . --fix` | Passed |
| `uv run ruff format .` | Passed |
| `uv run mypy .` | Passed, 315 source files |
| `uv run pytest -q`, both designated local databases configured | **2,259 passed, 1 skipped**, 18.41 seconds |
| `uv run alembic check`, local profile database | Passed; no new upgrade operations |
| `npm run api:generate` | Passed; generated contract/types unchanged |
| `npm run lint` | Passed |
| `npm run format:check` | Passed |
| `npm test -- --run` | **196 passed, 34 files** |
| `npm run build` | Passed, including TypeScript checking |
| `npm run test:e2e` | **14 passed**, desktop/mobile Chromium and V1 journeys |
| Backend Docker image build and isolated `/health` smoke | Passed |
| `git diff --check` | Passed |

The backend skip is the existing opt-in live Google Routes test, not an ignored
failure. No live Google/OpenTopoData route or real Neon session test was run in
this batch. Existing provider evidence remains in the M9 reports; this batch does
not establish new geographic coverage, road-grade calibration or staging readiness.
The existing Starlette/httpx deprecation warning remains.

Changed source: API preference mapping, typed preference patch/port/application
setters, PostgreSQL preference writes and default deletion coordination. Changed
test adapters implement that port; a new PostgreSQL/HTTP consistency suite adds
five cases. The real EIA integration test now takes an explicit current retrieval
clock. Documentation adds this acceptance matrix and updates architecture/README.
No files were deleted, no frontend product behavior was changed, and no migration,
private environment file or production setting was changed.

The remaining technical tradeoff is brief per-user write serialization: edits for
one user wait for that user's other preference/default deletion transaction.
Different users do not share this lock. Same-field last-transaction semantics and
cross-tab UI freshness are documented above; no versioned conflict UI is claimed.
Batch 1 is complete for the audited scope. Next is M10 batch 2, real session
lifecycle and staging acceptance; M10 as a whole is still open.
