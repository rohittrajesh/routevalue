# M10 batch 4: development EIA refresh and monitoring operations

Based on `b9fb442` on `v2`. This implements and activates a local macOS EIA
maintenance job against the pinned Neon V2 development database. There is no
hosted V2 deployment; this is not production scheduling or a 24/7 service.

## Delivered workflow

`eia_development_operations` validates the existing immutable development
Postgres/Auth target and connected schema before any refresh. Execution still
requires explicit `--execute --confirm-development-branch v2-development-routevalue`.
The original manual/local refresh entry points and their guards remain intact.
There is no new API endpoint, startup refresh, trip-request download or migration.

Under the existing PostgreSQL refresh advisory lock, each invocation:

1. Reads source health and snapshots before constructing an HTTP client.
2. Calculates the latest expected Monday observation using the existing
   holiday-aware Tuesday/Wednesday release calendar at 10 a.m. Eastern. This
   acquisition schedule does not extend the resolver's noon freshness deadline.
3. Downloads only missing/outdated regions. A current snapshot requires no
   downloader or timestamp update. California and national data remain separate,
   complete, grade-validated regional transactions.
4. Persists each region's attempt time **before** downloading, then throttles
   repeated attempts for one hour, including failure/crash cases. Shared database
   locking excludes concurrent refreshes; corrupt/future local state fails closed.
5. Rechecks real observation freshness. Downloading an unchanged stale workbook
   cannot produce a healthy outcome. Source observation dates are never rewritten.
6. Atomically replaces a private `latest.json` status report. Failed/partial
   refreshes report nonzero; previous valid stored snapshots survive failures.

Operational state is in ignored `backend/.runtime/eia`, excluded from the Docker
context. Files are written mode 0600 in a private directory. The attempt file is
bounded/versioned; latest execution evidence is bounded on read. Status output
contains region IDs, source/refresh/check timestamps and safe classifications, not
prices, emails, accounts, credentials, private hosts or raw exceptions.

`--status-only` reads local execution evidence without HTTP, SQL or file writes.
Missing, invalid, future-dated or over-two-hour-old evidence cannot report healthy.
It reports the last execution, not a fresh query of provider data; use the existing
read-only `eia_health_check` for authoritative snapshot freshness at the current
time. The job-management status command combines execution evidence, registration
and launchd's last exit code so a launcher failure cannot hide behind old success.

## Local schedule installed and checked

The user LaunchAgent `com.routevalue.v2-development.eia` runs at load and every
3,600 seconds. It uses this workspace's ignored `backend/.env.v2.local`, fixed
working directory and locked existing Python environment. Credentials are not
embedded in the plist. Its umask is 077. No KeepAlive/failure-spin loop is enabled.

Installed plist:
`~/Library/LaunchAgents/com.routevalue.v2-development.eia.plist`.
The tracked, reversible manager is `backend/scripts/manage_eia_development_job.py`.
From `backend/`:

```sh
# Verify the installed job and recent execution evidence.
PYTHONPATH=src uv run --env-file .env.v2.local \
  python scripts/manage_eia_development_job.py status

# Inspect recent local evidence without DB access or writes.
PYTHONPATH=src uv run python -m \
  routevalue.infrastructure.pricing.eia_development_operations \
  --status-only --state-directory .runtime/eia

# Check current persisted observation freshness, read-only.
PYTHONPATH=src uv run --env-file .env.v2.local \
  python -m routevalue.infrastructure.pricing.eia_health_check

# Run an explicitly authorized cycle now; retains retry throttling.
PYTHONPATH=src uv run --env-file .env.v2.local python -m \
  routevalue.infrastructure.pricing.eia_development_operations \
  --execute --confirm-development-branch v2-development-routevalue \
  --state-directory .runtime/eia

# Disable/remove only this managed job; retain state and price snapshots.
PYTHONPATH=src uv run python scripts/manage_eia_development_job.py uninstall \
  --confirm-development-branch v2-development-routevalue

# Reinstall/re-enable; verifies pinned target configuration.
PYTHONPATH=src uv run --env-file .env.v2.local \
  python scripts/manage_eia_development_job.py install \
  --confirm-development-branch v2-development-routevalue
```

The disable/re-enable path was executed and left the hourly job enabled with its
state retained. A subsequent actual launchd run exited **0**, reported healthy
and attempted **no downloads**, preserving the just-refreshed snapshot timestamps.
The first installer run exposed the installed uv runtime's handling of spaces in
absolute `--env-file` paths. That failure was reproduced independently; fixed
working-directory-relative arguments corrected it. Registration alone was not
accepted as evidence of successful execution.

## Live evidence

[Sanitized development evidence](validation/m10-eia-development-operations.json)
records these checks without account/profile values or credentials:

- Before refresh, both regional snapshots contained **October 12, 2026**
  observations and were unusable after the October 20 release deadline.
- The authorized runner made **two EIA workbook downloads**, refreshing only SCA
  and NUS. Both then contained **October 19** observations and all three grades
  were healthy. No Google Routes, Places or terrain request was needed.
- Six automatic-price resolutions succeeded using the real persisted provider,
  trusted Census geography and real release-aware resolver: regular, midgrade and
  premium for public California and North Carolina diagnostic origins. These
  lookups did not supply a manual price, write snapshots or download workbooks.
- Before/after aggregate fingerprints matched for users, auth identities, saved
  vehicles, preferences and terrain reservations. No nonpricing row was changed.
- The running app's price provider has no in-memory snapshot cache; it reads the
  persisted snapshots on subsequent automatic lookups. A backend restart is not
  required to see new source observations.

A prior verification probe ran while the just-reenabled job was still completing
and did not pass; the completed run was subsequently verified with exit 0 and
fresh status output. No intermediate registration/running state was called green.

## Failure recovery and scope limits

Actual local PostgreSQL plus generated valid XLS workbooks and controlled HTTP
verify partial failures, one-region retries, failed new-week preservation, recovery
after backoff, unchanged stale workbooks remaining unhealthy, advisory exclusion,
corrupt/future state, holiday/DST scheduling, rejected target/confirmation and stale
execution detection. Invalid HTTP never overwrites stored good snapshots; no test
weakens the actual freshness rules. The initial calendar fixture was corrected to
a date after the October holiday-delayed release, preserving the assertions.

Operational recovery:

- On nonzero status, inspect safe latest output and the private launcher error log,
  then run read-only source health. Check whether the job is unavailable, stale,
  contended, throttled, or whether EIA has not published usable new observations.
- Retry the guarded cycle after the one-hour attempt interval. Do not delete retry
  state, rewrite source dates, invent prices or change targets to manufacture a
  healthy monitor. Corrupt state/clock problems require explicit operator review.
- Disable the job with the manager when maintenance should stop; the uninstall
  path does not require usable database credentials and retains snapshot/state data.
- Automatic pricing continues to reject unusable data honestly. The existing
  manual gasoline override remains available without losing the trip.

This Mac must be available under the user's login for local scheduling. Sleep,
logout, lost network access, moved folders/runtime or branch changes can prevent
execution. The job follows code in this workspace; keep it on the tested V2 branch
and review operational changes before updating it. A live weekly boundary **under
unattended scheduling** has not yet been observed; the current release was refreshed
explicitly and scheduled healthy/no-download execution was observed separately.

There is **no outbound alert destination configured** and no email/Slack message
was sent. Nonzero exits and persisted/staleness-aware status are operational
signals, not proof of alert delivery. Hosted scheduling, monitored alert delivery,
secrets provisioning and observing subsequent unattended weekly recovery remain
explicit deployment/release checks. Local retry state coordinates this one managed
job; a hosted multi-instance scheduler will need one shared operational state/job
identity rather than separate local retry files. No new paid service was enabled.

## Final gates and changed files

| Executed gate | Final result |
| --- | --- |
| `uv run ruff check . --fix` | Passed |
| `uv run ruff format .` | Passed |
| `uv run mypy .` | Passed, 322 source files |
| `uv run pytest -q`, both designated local databases | **2,291 passed, 1 skipped** |
| `npm run api:generate` / `npm run api:check` | Passed; no contract/type changes |
| `npm run lint` | Passed |
| `npm run format:check` | Passed |
| `npm test -- --run` | **205 passed, 34 files** |
| `npm run build` | Passed |
| `npm run test:e2e` | **20 passed**, V1/V2 desktop/mobile journeys |
| Backend Docker image build | Passed |
| Live pinned-target refresh, six resolver reads, data preservation | Passed |
| launchd actual execution and disable/re-enable recovery | Passed |

The sole backend skip is the opt-in live Google Routes test; no new terrain
coverage is claimed in this batch. Existing Starlette/httpx/browser warnings remain.
No TypeScript source, migrations, production configuration or private env values
changed. New tracked files are the guarded runner, job manager, operations tests,
this report and sanitized evidence; updated files are publication acquisition
scheduling, ignore rules and architecture/operations/README documentation. No files
were deleted. Runtime state and the user LaunchAgent remain local artifacts.

M10 batch 4 is complete for the authorized local/pinned-development scope. M10
as a whole remains open for final integrated acceptance and unresolved release
checks, including hosted scheduling/alerts and authentication/recovery. M11 still
requires explicit production approval, exact-release verification, rollback,
merge/deployment and tagging. This batch did not merge `main`, deploy production
or claim an always-on V2 website.
