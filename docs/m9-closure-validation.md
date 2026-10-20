# M9 closure: complete persisted energy preferences and reconcile architecture

Implemented against base commit `ac33373` on `v2`. All changes are in
`/Users/roi29/Documents/ChatGPT/RouteValue CS Project`; the original Desktop
checkout/configuration files were preserved. See Git history for the subsequent
user-approved commit/push. No `main` merge, production deployment or paid service
activation was performed.

## Delivered behavior

- Optional `electricity_price_per_kwh` persists as an exact Decimal. Zero is valid;
  null/unset does not invent a rate. Normal EV comparisons use the authenticated
  saved rate without sending an electricity price in the trip request. Explicit
  trip overrides retain precedence and do not alter storage.
- The settings UI saves/clears the electricity rate and loads it on a new session
  or page reload. Missing rates produce an actionable
  `electricity_price_not_configured` response before route acquisition. Saved-rate
  and explicit-input provenance are distinct in the response and results UI.
- Optional `preferred_fuel_market` persists a selected purchasing area's display
  name/coordinates. No home address or provider identifier is required. The
  authoritative server geography resolver selects pricing jurisdiction from those
  coordinates, not labels or a browser-supplied EIA region.
- Preferred-market pricing takes precedence over trip origin. Clearing restores
  origin pricing without changing route endpoints. Unsupported saved areas fail
  honestly; manual gasoline pricing still bypasses the automatic lookup.
- Sparse updates preserve omitted fields. Explicit null clears only that setting.
  Changing value of time/defaults or deleting the default vehicle preserves energy
  preferences. Account isolation and vehicle ownership remain enforced.
- Preference changes invalidate obsolete/in-flight results; trip locations survive.
  The existing gasoline/EV terrain models and shared baseline policy are preserved.
- [Architecture decisions](v2-architecture-decisions.md) explicitly distinguish the
  implemented OpenTopoData/EIA/email-password workflow from the original Google
  Elevation/Places station-pricing/Google OAuth plans. Those original provider
  integrations are not advertised as shipped and remain scope/release decisions.

## Migration and development activation

`a19d6e2c740b` adds four nullable columns and validation constraints to the existing
preferences table. Existing rows retain their original fields, and new fields are
unset. It chains after the quota-table migration. Neither migration removes data;
schema downgrade deliberately refuses to drop retained preference/quota history.

Both disposable local test databases were migrated and passed `alembic check`.
After local gates passed, the pinned Neon V2 development target was verified using
the existing database/Auth branch guards, then upgraded from `e8a1d4c209bf` to
`a19d6e2c740b`. Application and direct migration URLs were checked to target the
same branch. Aggregate fingerprints before/after confirmed all existing data in
users, auth identities, saved vehicles, legacy preference fields and EIA pricing
tables was unchanged. No user rate or fuel market was assumed/populated.

[Sanitized migration evidence](validation/m9-development-preferences-migration.json)
contains only the target classification, revisions, table names and verification
booleans. Credentials, account records and data fingerprints are not published.
The development backend was restarted with the existing private configuration.
Production was not accessed or modified.

## Final executed gates

| Check | Result |
| --- | --- |
| `uv run ruff check . --fix` | Passed |
| `uv run ruff format .` | Passed; 314 files unchanged in final run |
| `uv run mypy .` | Passed; 314 source files |
| `uv run pytest -q`, designated local databases configured | **2,254 passed, 1 skipped** |
| Additive migration and `alembic check`, both local databases | Passed |
| Guarded development migration/data preservation and schema check | Passed |
| `npm run api:generate` | Passed; OpenAPI and TypeScript regenerated |
| `npm run lint` | Passed |
| `npm run format:check` | Passed |
| `npm test -- --run` | **196 passed, 34 files** |
| `npm run build` | Passed |
| `npm run test:e2e` | **14 passed**, desktop/mobile Chromium and V1 regressions |
| Desktop/mobile energy-settings screenshot inspection | Passed |
| Backend Docker build, `/health`, new OpenAPI preference fields | Passed |
| `git diff --check` | Passed |

The sole backend skip is the opt-in live Google Routes smoke test. It was not
rerun in this batch. Prior live route evidence is preserved in the earlier batch
reports; this batch does not claim new universal terrain coverage or model
calibration. One existing Starlette/httpx deprecation warning remains.

Debugging corrected a real accessibility issue where helper text became part of
the electricity input's accessible name. Regression expectations now assert the
new specific missing-rate error instead of misclassifying absent configuration as
a powertrain mismatch. Invalid rates, contradictory energy inputs, spoofed/partial
markets and database constraint failures still reject; tests were not weakened.

PostgreSQL/HTTP coverage verifies exact saved-rate reuse, zero, override precedence,
clearing, default deletion, user isolation and atomic rejection of invalid PATCHes.
The preferred-market integration uses the real Census boundary resolver to prove
that a misleading California label on NC coordinates cannot select California
pricing. Browser journeys test save/reload/reuse/override/clear, retained locations
and responsive layout with controlled identity/storage/upstream fixtures. Those
fixtures are not production authentication bypasses.

## Changed-file scope and closure

New: additive migration, PostgreSQL/HTTP preference integration suite, energy
settings component/unit tests, architecture decision record, this report and safe
development migration evidence. Updated: preference/profile/persistence models,
API PATCH/response/evaluation schemas, both evaluation paths, result provenance,
planner/settings UI, generated contract/types, browser fixtures/journeys,
schema/revision/contract assertions, CI head verification, README and runbook.
No source files were deleted.

M9's implemented desktop/mobile product workflow is complete with the documented
provider/authentication scope. No additional M9 UI gap identified in the prior
consolidation remains. This is not a claim that every original provider proposal
has shipped or that V2 is production-ready.

M10 remains responsible for integrated release acceptance, deployed/staging real
session lifecycle checks, shared quota enablement across workers, EIA refresh and
monitor scheduling/observation, failure recovery and cost-control verification.
The development migration created the quota table but did not switch its running
process-mode configuration. Production provider/authentication scope must be
reviewed before release. M11 covers approved production migrations/configuration,
exact-commit smoke tests, rollback verification, merge/deployment and release tag.
