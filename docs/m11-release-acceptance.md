# M11 production release acceptance

Status: production provisioning completed; application deployment and hosted owner
acceptance are in progress. This document does not declare M11 complete.

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
  Hosted image checks remain to be recorded.

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
