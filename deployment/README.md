# V2 release configuration

Production is an explicit target, never the existing Neon default branch or the
pinned development database. `production-target.json` contains the reviewed
nonsecret branch/database/role/Auth endpoint identifiers for the approved isolated project. A
missing manifest, wrong branch, development endpoint, mismatched pooled/direct
URL or Auth configuration fails closed before any download/write.

Cloudflare Pages production build settings (public values, no DB/server keys):

```dotenv
NODE_VERSION=24
VITE_API_BASE_URL=https://routevalue-api.onrender.com
VITE_V2_API_BASE_URL=https://routevalue-api.onrender.com/api/v2
VITE_V2_HOMEPAGE=1
VITE_AUTH_URL=<approved-production-Neon-Auth-URL>
VITE_GOOGLE_MAPS_API_KEY=<existing-browser-restricted-key>
```

Build root remains `frontend`, command `npm run build`, output `dist`. V2 is the
homepage only when `VITE_V2_HOMEPAGE=1`; `/v2` remains compatible and `/v1` retains
the existing V1 UI. Remove/disable the homepage setting and rebuild to roll back
the frontend entry point. Preserve database schemas and accounting history during
application rollback. Existing V1 API origin/paths are unchanged; V2 retains its
actual `/api/v2` prefix when it bypasses Vite's development proxy.

Production-bundle checks: from `frontend`, run `npm run test:release`. These build
the real production entry points and Neon SDK, with synthetic HTTP endpoints and
no real keys, provider calls or account mutations. Desktop/mobile verify root,
reload, legacy V1, `/v2`, direct reset links and honest OTP rejection. This does not
certify Cloudflare SPA behavior, a real hosted cookie session or live providers;
repeat those checks against the actual deployed release.

The production EIA workflow runs on `main` only, in the `production` GitHub
Environment. Restrict that environment to `main`. Its secret names are
`ROUTEVALUE_PRODUCTION_DATABASE_URL` and
`ROUTEVALUE_PRODUCTION_DATABASE_URL_UNPOOLED`; variables are
`ROUTEVALUE_PRODUCTION_AUTH_URL`, `ROUTEVALUE_PRODUCTION_JWKS_URL`, and
`ROUTEVALUE_PRODUCTION_EIA_ENABLED=true` after target/configuration verification.
Never put these DB secrets into frontend settings, workflow files, artifacts or
ordinary CI test environments. GitHub workflow success while operations are
explicitly disabled is not a healthy pricing observation.

Hosted retry attempts are committed in `public.eia_refresh_attempts` before HTTP,
under the existing global PostgreSQL refresh advisory lock. A fresh runner keeps
the same one-hour failed-attempt backoff. Lost commit acknowledgement cannot start
HTTP; future state fails closed. Refreshes retain actual source observation dates;
stale downloads cannot report healthy. Only the existing two public EIA workbooks
are acquired, outside request/startup paths. No Mac-local retry file is required.

Run read-only target/pricing health with the intended production env loaded:

```sh
PYTHONPATH=src uv run --env-file .env.v2.production.local python -m \
  routevalue.infrastructure.pricing.eia_production_operations --check \
  --target-manifest ../deployment/production-target.json
```

An explicitly authorized seed/maintenance invocation uses `--execute
--confirm-production-branch v2-production-routevalue` in place of `--check`.
Migration/role provisioning uses separate private owner credentials; the runtime
and maintenance runner do not need schema-owner or Auth-schema permissions.

GitHub schedules can be delayed; this is an hourly maintenance attempt, not an
exact-time SLA. A failed run is a failure signal, not proof someone received an
alert. Configure/verify operator notifications and observe an unattended weekly
publication boundary before claiming those operating checks passed. Do not keep
Render awake using this scheduler; it reads/writes only the approved Neon target
and EIA sources. No new paid scheduler or keep-alive service is included.
