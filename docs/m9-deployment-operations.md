# V2 terrain and EIA operations

This runbook prepares deployment; it does not authorize production configuration
changes. V1 production and its `main` deployment remain unchanged. Commands run
from this workspace's `backend` directory, not the older Desktop checkout.

The current schema head is `a19d6e2c740b`, which also adds nullable saved electricity
rate/fuel-market fields. The final M9 batch applied both additive migrations to
the pinned V2 development branch and verified existing business data unchanged.
Production migrations remain a separate M11 release step. See
[architecture decisions](v2-architecture-decisions.md) and
[M9 closure validation](m9-closure-validation.md).

## Shared terrain accounting

Migration `f2b7c39a106d` adds `public.elevation_call_reservations` and an index. It
does not alter profiles, vehicles, preferences, pricing or Neon Auth tables. No
startup or request handler creates tables. Only random UUIDs and timestamps are
stored; reservations older than 48 hours are pruned under the quota lock. Active
rolling 24-hour history is retained. The migration deliberately refuses schema
downgrade because dropping quota history could permit excess calls.

Before enabling shared mode in a target environment:

1. Verify the exact database/branch and its schema privately. For pinned V2
   development, use the existing protected EIA `--check` command. Production
   identity/configuration requires a separate release approval.
2. Review the additive migration and arrange normal database backup/rollback
   procedures. The application role needs SELECT/INSERT/DELETE on the quota table.
3. Apply `uv run --env-file /path/to/target.env alembic upgrade head`, then
   `uv run --env-file /path/to/target.env alembic check`. Never paste connection
   strings into commands/logs. Initial quota validation migrated only disposable
   local databases; the final preference batch also migrated pinned V2 development.
4. Configure the target privately:

   ```dotenv
   ROUTEVALUE_TERRAIN_LIVE_ENABLED=1
   ROUTEVALUE_TERRAIN_QUOTA_MODE=postgres
   ROUTEVALUE_TERRAIN_REQUESTS_PER_TRIP=6
   ROUTEVALUE_TERRAIN_SINGLE_PROCESS_DEV=0
   ```

5. Verify every worker uses the same quota database/configuration. Separate
   databases do not coordinate, even behind the same upstream IP. All application
   traffic sharing that IP must use one gate. Other applications on shared hosting
   may still consume public-provider limits; HTTP 429 falls back.
6. Test a public route with explicit manual diagnostic mass and inspect terrain
   status. Test missing mass and blocked acquisition for baseline recovery. Do not
   infer accurate road grade from complete raster observations.

Reservations use PostgreSQL time, a transaction advisory lock, a two-second lock
timeout and five-second statement timeout. Connection establishment/pooling retain
their normal timeouts. Failed quota access blocks upstream calls; it never silently
switches to the process limiter. Contention can produce conservative baseline
fallback before the daily allowance is exhausted. No automatic HTTP retries or
quota refunds occur. Failed HTTP attempts and process crashes after reservation
remain counted. A connection/commit failure prevents HTTP, even if a reservation
may have committed before its acknowledgement was lost.

For application rollback, disable live terrain or roll back code while leaving
the quota table/revision intact. Existing EIA refresh CLIs recognize both the
previous EIA schema, additive quota schema and energy-preference schema. Deleting quota history or changing
from shared to process mode mid-day requires review of the upstream allowance;
it is not a recovery mechanism.

## M10 development activation and read-only quota health

M10 batch 3 activated shared mode only for the local V2 backend and pinned Neon
V2 development database. Its private launch configuration is now the ignored
`backend/.env.v2.local` in the project workspace; the older Desktop file is
preserved. The settings are live=1, quota mode=postgres, six calls/trip and
single-process confirmation=0. No production target was configured. See
[M10 batch 3 validation](m10-batch-3-shared-terrain.md).

Read shared accounting without reserving calls, pruning history or contacting any
external elevation/routing provider:

```sh
PYTHONPATH=src uv run --env-file .env.v2.local \
  python -m routevalue.api.terrain_quota_health
```

Exit 0 means shared mode was enabled, permissions were present and the observed
quota snapshot was usable. Exit 1 covers disabled/process-only mode, exhaustion,
future-clock state, missing table, permission failure or database unavailability;
2 means invalid configuration. JSON distinguishes these states when detectable.
It reports usage/remaining counts, limits and timestamps without credentials,
connection URLs or account identifiers. It sets a five-second SQL statement
timeout; engine connection/pool establishment retain their existing timeouts.
“Ready” is an observation, not a reservation or guarantee against concurrent use.
Provider IP limits can also include unrelated traffic outside this ledger.

Never truncate/delete the ledger to recover quota. Disable live terrain while
leaving PostgreSQL mode/history intact if acquisition needs to stop. Existing
process-local history cannot be reconstructed by this command: migrations between
modes need a usage review, and the first shared window is not proof of accounting
for attempts made before activation. Multiple workers/instances must all use this
same configuration/database; a process-mode worker would bypass shared accounting.

## Request budget and price

Verified October 19, 2026:

- [OpenTopoData](https://www.opentopodata.org/) publishes a free API with limits
  of 100 points/request, one call/second and 1,000 calls/day. RouteValue retains
  100-point batches, a 1.1-second interval and 900 calls per rolling day. The trip
  allowance increases from five to six at no added elevation-provider charge. At
  six attempts/trip this permits at most 150 such trips in a fully available
  900-call rolling window; trips using fewer calls consume less.
- [Google Elevation pricing](https://developers.google.com/maps/billing-and-pricing/pricing)
  lists 5,000 free events/month and then $5/1,000 in the first paid tier. Under
  that tariff, 7,000 total events would yield $10 in usage charges if the free
  allowance remains available. Usage aggregates across the billing account.
  Taxes, existing Maps/Routes/Places costs and other projects are outside that
  arithmetic. This is an estimate, not an enforced account bill cap.
- Google Elevation was not enabled or implemented here. A paid switch requires
  billing-account verification, durable monthly metering and provider-side quota
  controls before promising a $10 ceiling. The current free increase addresses
  the observed per-trip constraint without it.

Public availability, shared hosting IPs, database compute/storage usage and pricing
changes remain operating considerations. No new paid subscription or cloud setting
was created. Neon Free is not an unlimited-throughput guarantee.

## EIA monitoring and refresh

Read-only health command, with the intended environment loaded privately:

```sh
PYTHONPATH=src uv run --env-file /path/to/target.env \
  python -m routevalue.infrastructure.pricing.eia_health_check
```

Exit 0 means both California and national snapshots have all three usable grades;
1 means missing/unusable/unavailable data; 2 means invalid DB configuration. Output
contains only region IDs, statuses and original timestamps. This neither downloads
workbooks nor changes observation dates. A fresh national fallback does not hide
an unhealthy California snapshot.

Recommended deployment procedure: run this monitor hourly and after refresh;
alert on nonzero status. Fetch new weekly data after its Tuesday release, or
Wednesday for a release holiday, then rerun the monitor. The existing development
refresh requires explicit pinned-branch confirmation; do not repurpose it for
production. Preserve coordinator/advisory locking in a deployment scheduler. Never
refresh during a trip request.

M10 batch 4 installed a guarded hourly local development LaunchAgent and verified
actual no-download execution after restoring current source observations. See
[M10 EIA operations](m10-batch-4-eia-operations.md) for commands, status/staleness,
retry, disable/re-enable and evidence. No hosted/production scheduler or outbound
alert delivery is configured. Provisioning that target, secrets/alerts and
observing a subsequent unattended weekly release remain release checks. A monitor
detects failed refreshes; it cannot manufacture unpublished source observations.
