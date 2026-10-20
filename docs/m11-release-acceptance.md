# M11 production release acceptance

Status: V2 production deployment and the selected owner acceptance are complete.
The owner confirmed reset-email receipt and explicitly declined changing the
password again. Production SMTP hardening and longer-running operating
observations remain open; this record does not claim every launch checklist item
or future operating event has passed.

## Approved isolated target

The owner explicitly approved a new Free-plan Neon project, additive migrations
from an empty database, and a restricted runtime role. Project `RouteValue V2
Production` (`nameless-wind-97233593`) is in AWS Oregon, PostgreSQL 18, database
`neondb`, branch `v2-production-routevalue` (`br-blue-pine-arsilhqr`). The reviewed
nonsecret connection identities are in `deployment/production-target.json`.

Migrations were applied from empty through `d41e7a902b63`; Alembic reported no
pending schema changes. The runtime role has public-schema usage and CRUD on the
eight application/operations tables, SELECT-only migration tracking, no ownership,
no schema CREATE, no Auth-schema usage, and no superuser/create-role/create-database
or replication privileges. Owner credentials remain only in the ignored private
local environment. No baseline stamp or schema drop was used.

An earlier schema-only branch in the original Neon project could not provision
Auth because its cloned Auth schema already existed. It remains unused and was
not dropped or stamped. The original default and development branches remain
unchanged. It must not be confused with the separate production project above.

Production Auth application name is RouteValue. Its trusted origin is
`https://routevalue.pages.dev`, with localhost disabled. Email signup/signin are
enabled; signup verification remains at the new project's default off setting.
The application exposes email/password authentication, not Google OAuth.

Initial production EIA refresh downloaded the two supported public workbooks and
persisted healthy SCA and NUS snapshots for every supported grade, observed
2026-10-19. The new shared attempt table records retry state across hosted runners.
This initial seed does not prove unattended weekly refresh or alert delivery.

A diagnostic output briefly exposed the initial runtime password. It was revoked
by rotating the same limited role before hosting provisioning; the replacement
was tested and saved privately. No permission expansion resulted. Neither password
belongs in source, artifacts or this record.

## Hosting preparation

Existing Cloudflare Pages `routevalue` and Render `routevalue-api` remain the
hosting services. Existing Google server/browser keys are preserved. The approved
runtime credentials are provisioned only to Render and encrypted GitHub production
secrets; Cloudflare receives public Vite settings. The GitHub `production`
environment is restricted to `main`. The new hourly EIA workflow uses the reviewed
target and restricted role; ordinary CI continues to use disposable local databases.

The frontend production API prefix is `/api/v2`; a regression fixes absolute-host
configuration that previously produced `/v2`. The optional production homepage
flag selects V2 at `/`, retaining V1 at `/v1` and compatibility at `/v2`.

## Executed local release checks

- Ordered backend Ruff check/fix, Ruff format and mypy: passed (328 source files).
- Complete backend suite: 2,308 passed, one opt-in live test skipped. PostgreSQL
  integrations used only the two designated disposable databases on port 55432.
- Frontend OpenAPI generation, lint, format check, strict build: passed.
- Frontend unit/component tests: 252 passed in 38 files.
- Desktop/mobile application browser suite: 30 passed.
- Production-bundle browser suite: eight passed after release metadata update.
- Final Docker image build, isolated health endpoint and V2 OpenAPI smoke passed.
  Hosted health, generated-contract equality and origin checks passed.

## Required hosted evidence before closure

Record exact commit/CI/deployment identities; backend health and contract; allowed
and rejected CORS origins; V2 homepage, legacy V1 and direct SPA/reset routes;
owner-controlled production signup/signin/reload/signout/password recovery; live
gasoline automatic/manual pricing and EV preferences; representative terrain
results and truthful fallbacks; shared quota/budget health; production maintenance
workflow and rollback instructions. Provider availability remains route-dependent.

Operator notification delivery and an unattended EIA publication boundary cannot
be inferred from a successful manual seed. Record these as follow-up operating
observations if they cannot be observed during release. No paid upgrade or
keep-alive service is authorized or provisioned.

## Deployed release evidence (2026-10-20)

Release application commit: `b2f102ddbeb97c86399f596cdc8a7db4fd17f07f`,
fast-forwarded from `v2` to `main` after all four CI jobs passed. CI also passed
on `main`: [release CI](https://github.com/rohittrajesh/routevalue/actions/runs/39506411626).
The working directory remains the user's RouteValue project on branch `v2`.

- Render deployment `dep-dbbue02fngtc73a81p30`: succeeded/live at the exact release
  commit. Public `/health` returned 200; all 12 OpenAPI paths and the entire schema
  matched the generated contract. `/api/v2/me` without credentials returned 401;
  production origin preflight returned 200, unrelated-origin preflight 400.
  [Backend evidence](validation/m11-hosted-backend.json).
- Cloudflare production deployment `1e11e3aa-de27-4010-baa0-3326b6dba30e`:
  succeeded at the same release commit. `https://routevalue.pages.dev/` and direct
  `/v2` loaded the production V2 sign-in screen. A direct reset route loaded the
  SPA, removed the synthetic token from the address, and showed a missing/invalid
  link after reload. No real password/reset code was submitted by the agent.
- `/v1` preserved the legacy planner. A real San Diego–Julian trip used Google
  autocomplete, route evaluation and map rendering successfully: two eligible
  alternatives, recommended personalized cost $44.26 with explicitly entered
  30 MPG, $4.50/gallon and $24/hour. These are smoke-test inputs, not a claim about
  a user's vehicle or current gasoline quote.
- [Hosted EIA run #1](https://github.com/rohittrajesh/routevalue/actions/runs/39506620290)
  passed, with its actual guarded operations step executed. Both regions/all
  grades were healthy before and after; no workbook download was due. This is
  distinct from the earlier real two-workbook seed. [Run output](validation/m11-hosted-eia.json).
- Production-configured terrain diagnostics applied gasoline and EV terrain energy
  on San Diego–Julian, Denver–Idaho Springs and Asheville–Cherokee. Missing mass
  produced exact baseline costs. The completed run made six Google requests and
  14 OpenTopoData requests; an earlier stopped harness made three Google requests
  and six elevation requests before its too-small test cap blocked further HTTP.
  All 20 elevation attempts were counted in shared production SQL. No account row
  counts changed. [Inputs, results and limitations](validation/m11-production-terrain.json).
  These are real provider/domain diagnostics using production configuration, not
  authenticated requests through the hosted API or universal coverage evidence.

Render's specific-commit deployment temporarily disabled auto-deploy; after main
CI passed, it was explicitly set to **After CI Checks Pass** for future main
releases. Cloudflare retains its existing automatic main deployments.

## Remaining owner and operating acceptance

The owner created and signed into the production account. Real hosted profile,
preference CRUD, default vehicle, reload persistence and cross-tab sign-out passed.
Two live catalog vehicles were saved: a 2023 Camry LE/SE and a 2021 Tesla Model 3
Standard Range Plus RWD. Gasoline trips verified preferred-market national EIA
pricing, clearing to California trip-origin pricing, manual override, missing-mass
baseline and manual-mass terrain. EV trips verified the persisted $0.25/kWh rate,
baseline/terrain, a $0.30 trip override that retained the saved rate, and manual
mass add/update/clear with source notes. Both temporary illustrative weights were
cleared. The two catalog test vehicles, $24/hour and $0.25/kWh example settings
remain for the owner to review; they are not asserted to describe the owner's car
or electricity tariff. [Hosted journey evidence](validation/m11-hosted-owner-journeys.json).

A requested 390-pixel viewport was limited by the browser to 662 CSS pixels. The
hosted narrow layout had no horizontal overflow; this does not certify a hosted
390-pixel mobile session. Desktop and Pixel 7-sized synthetic browser suites and
real-production-bundle suites passed separately. The viewport override was reset.

Production recovery sent a controlled request to the observed production account.
Neon returned HTTP 200 with `success: true`, no error code and no Retry-After.
The owner then confirmed receipt and explicitly chose not to change the password
again. New-password sign-in in this production environment is therefore not
claimed tested. The owner subsequently returned to the authenticated production
profile; its saved vehicles/settings remained present. M10's separate local
password-change acceptance remains separate evidence.

The browser redacts email input values. An initial apparent address mismatch was
invalid evidence and was withdrawn; no cause is asserted for the earlier missing
email. A successful request is not inbox delivery proof by itself—the owner's
confirmation supplies the receipt observation. The agent read/submitted no code
or password. [Recovery probe](validation/m11-production-recovery.json).

Neon's [production checklist](https://neon.com/docs/auth/production-checklist)
identifies its shared sender as a development/testing service and calls for
custom SMTP for production deliverability and higher limits. Password-reset codes
can work with the shared sender, as the owner observed. Custom SMTP is still an
explicit hardening follow-up: no provider credentials were present, no external
email service was added and no paid plan was authorized. This release does not
certify sustained delivery or attribute the missing message to throttling.


The hourly schedule is configured, but its first unattended scheduled invocation,
next publication-boundary recovery and operator notification delivery are still
unobserved. A manually dispatched healthy job proves none of those future events.
No paid service, compute upgrade or keep-alive loop was added. The existing Render tier was verified as $7/month, 0.5 CPU/512 MB, one instance;
no tier change was made. Neon production uses Free. Resource limits still apply;
this release is not an uptime SLA.

## Rollback

Keep the additive production schema, pricing snapshots and quota/attempt history.
For an application rollback, redeploy the earlier known V1 Render commit
`cfeb44edba413e99800cebc936699b378edc0123` and restore Cloudflare's prior production
deployment `e9447bf3-dee4-48d8-9f55-4578c7dcf013`; both identifiers were verified
before release. Alternatively disable `VITE_V2_HOMEPAGE` and rebuild to restore
V1 at `/` while retaining the compatible V2 backend. Never downgrade/drop the
production tables or repoint runtime to development. Exact-commit Render rollback
turns auto-deploy off; review it before a subsequent release. Do not report a
rollback as tested: these targets were identified, not deliberately activated.

## Post-journey runtime check

Read-only SQL verified two saved vehicles with no stored mass, and confirmed the
runtime role still cannot CREATE the public schema, access the Auth schema or
update migration tracking. Shared elevation accounting was ready with 52 of 900
rolling daily reservations consumed and 848 remaining at 2026-10-20T22:25:34Z.
All workers retain six requests per trip and a minimum 1.1-second interval. These
are configured safety limits and observed reservation counts, not measured
Google billing or a guarantee of universal elevation coverage.
[Runtime/quota evidence](validation/m11-production-quota.json).

## Release scope

Implementation changes, tests, runbook, nonsecret target manifest and acceptance
evidence are committed in the user's project and pushed to GitHub. No development
accounts were copied to production. All application changes were deployed from
CI-green `b2f102d`; subsequent release-record changes contain documentation and
nonsecret evidence only. The release tag is created after the final CI check.
Owner account creation and credential entry remained owner-controlled.
