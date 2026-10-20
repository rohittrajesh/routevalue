# Local V2 terrain validation

Use `http://localhost:5173/v2` for the real app. The current development Neon Auth
configuration accepts `localhost`; authenticated requests from `127.0.0.1:5173`
are rejected as `INVALID_ORIGIN`. CORS preflight alone does not establish that an
origin passes Better Auth's authentication checks. Production configuration was
not changed to fix this.

## Configuration and preflight

`backend/.env.example` documents the required names without credentials. Keep real
values in an ignored local environment file. This session used the existing files
in the older `/Users/roi29/Desktop/Project1/routevalue` checkout, read privately.
Its uncommitted manufacturer-weight experiment and other changes were not edited.
M10 batch 3 subsequently created the active ignored `backend/.env.v2.local` in this
workspace with the same pinned development credentials and shared quota settings;
the original file remains unchanged.
The implementation lives in this chat's workspace.

From `backend`, check an existing configuration without making external calls:

```sh
PYTHONPATH=src uv run --env-file /path/to/backend/.env.v2.local \
  python -m routevalue.api.terrain_diagnostics
```

The command reports safe configuration presence and quota settings. It does not print URLs, keys, tokens, account
identifiers, or database credentials.

Real terrain requires `ROUTEVALUE_TERRAIN_LIVE_ENABLED=1`. The default
`ROUTEVALUE_TERRAIN_QUOTA_MODE=process` also requires
`ROUTEVALUE_TERRAIN_SINGLE_PROCESS_DEV=1` and one backend process.
`ROUTEVALUE_TERRAIN_QUOTA_MODE=postgres` uses shared durable accounting and requires
the additive quota migration. Both modes pair acquisition with Google
`HIGH_QUALITY` geometry. Live acquisition remains disabled by default; this work
did not enable it in production. See [deployment operations](m9-deployment-operations.md).

## Reproducible diagnostics from a route export

The diagnostics command accepts a normalized API JSON export with
`route_evaluations`, each containing `route` and optional `geometry`. It ignores
other response fields. Files are limited to two megabytes and six candidates.
Supply explicit vehicle/economic diagnostic inputs; the tool invents no defaults.

```sh
PYTHONPATH=src uv run --env-file /path/to/backend/.env.v2.local \
  python -m routevalue.api.terrain_diagnostics \
  --routes-file /private/tmp/routes.json \
  --mass-kg 1800 --mpg 30 --gas-price 4.50 \
  --kwh-per-mile 0.30 --electricity-price 0.25 --value-of-time 24
```

Without `--execute` this makes no external calls and verifies baseline behavior.
For public OpenTopoData acquisition, additionally pass `--execute` and
`--confirm-high-quality-geometry`, with the live flag and selected quota mode configured.
Only confirm geometry obtained from the actual high-quality Google configuration.
The confirmation is user-supplied provenance, not an independent accuracy check.
The tool never calls Google, changes profiles or refreshes gasoline prices. Both
energy models reuse one acquired terrain dataset, and the report compares actual
energy costs with their exact baseline costs.

## Budget and accuracy behavior

The live default is six public elevation calls per trip, 900 per rolling 24 hours,
at least 1.1 seconds apart. Set `ROUTEVALUE_TERRAIN_REQUESTS_PER_TRIP` to exactly
`5` to retain the previous trip allowance, or `6` for the new default. Every
attempted call consumes budget; no automatic elevation retry occurs. This is a
free-provider allowance increase; no paid endpoint was activated.

Live composition now distributes sampling capacity across distinct candidate
geometries, using the existing bounded sampler to increase spacing when necessary.
Identical geometry and distance can share observations while retaining separate
candidate indices, tolls, durations and economic evaluations. Trip allowances reset
on each acquisition; the shared rolling daily gate does not. Default acquisition
without a trip budget retains the existing sampling behavior.

Coarser spacing can miss short hills. Complete elevation observations and normalized
usable coverage do not prove road-grade accuracy. Missing data, untrusted geometry,
coverage failures, missing manual mass or exhausted budgets still trigger a shared
baseline. More than six distinct shapes can still exceed the budget. No candidate
is silently dropped to manufacture terrain availability. Six distinct shapes can
receive one batch each; fewer shapes may receive more samples within the budget.

The default process limiter remains development-only: restarts do not preserve its
history. PostgreSQL mode commits reservations before HTTP and shares them across
workers/restarts, using database time and transaction advisory locking. Missing
migrations, database errors and lock contention block upstream calls and produce
baseline fallback. All workers sharing an upstream IP must use the same database
and mode. Unrelated consumers of that IP remain outside this accounting.

## EIA publication cadence

EIA's March 2025 notice moved publication to Tuesday around 10 a.m. Eastern, or
Wednesday when a Monday or Tuesday federal holiday delays the release, while
observations remain dated Monday.
See the [publication notice](https://www.eia.gov/petroleum/gasdiesel/notice.php) and
[current release schedule](https://www.eia.gov/petroleum/gasdiesel/schedule.php).

An exact seven-day age limit incorrectly rejects the latest available EIA data
each Monday. The V2 EIA resolver now accepts normalized Monday observations through
the next expected publication day at noon Eastern: the scheduled 10 a.m. release
plus a bounded two-hour delivery/refresh allowance. It handles recurring Monday
or Tuesday federal holidays and Eastern daylight-saving changes, rejects future observations,
and imposes a ten-day absolute ceiling. It never modifies the original observation
or publication timestamps. Non-EIA quotes and the V1 domain freshness policy retain
their existing rules.

Refreshing the development cache alone did not fix the Monday failure: the source
correctly still contained October 12 observations before the October 20 release.
After the schedule fix, all three real development gasoline grades resolved without
invented prices. Manual price overrides remain available and retain precedence.

The app continues to read persisted prices rather than refreshing workbooks during
a trip. The read-only `eia_health_check` command now checks every supported
region/grade using the actual resolver expiry policy. Production refresh scheduling
must still be configured and verified separately; this work did not alter production
services. See [the operations guide](m9-deployment-operations.md).

## Browser tests

```sh
cd frontend
npm run test:e2e
```

Playwright starts Vite and a loopback FastAPI fixture app, testing desktop Chromium
and Pixel 7-sized Chromium. V2 trips are real HTTP calls into the real application,
domain, schema and response-mapping code. Only identity verification, storage and
external providers are controlled fakes; production Neon Auth is unchanged.
`backend/tests/browser_server.py` requires explicit test-only enablement and is
never imported by the production app. Accounts are isolated per browser test.
The E2E configuration cannot reuse unrelated servers and exists separately from
the real development configuration. CI installs the locked backend environment
for this browser test job.

These tests complement PostgreSQL integration and real-provider checks; they do
not establish that real OAuth/session cookies or production deployment work.
