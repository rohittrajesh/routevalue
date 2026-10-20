# M10 batch 2: session lifecycle and development acceptance

Based on `381549d` on `v2`. The user confirmed there is no dedicated V2 staging
deployment and selected local frontend/backend with the pinned Neon development
branch for this batch. This report certifies that bounded environment, not hosted
staging, production readiness or completion of all M10 work.

## Delivered hardening

- An API 401 or missing JWT now removes the private workspace and offers sign-in,
  even when the SDK still reports cached authenticated user data. Profile editors,
  garage, planner and previous results unmount together. No credentials or bearer
  tokens are stored by the new session-boundary module.
- Successful real SDK sign-out clears the workspace immediately. Failed sign-out
  keeps a safe retry message; it does not claim the server session was terminated.
- Successful same-account reauthentication reloads saved data. Failed credentials
  cannot release the reauthentication boundary. A provider 503/network failure
  remains a recoverable availability error rather than being treated as sign-out.
- Requests capture a session generation before obtaining a token. Detected account
  changes/sign-out invalidate pending token retrieval and old responses; old 401s
  cannot invalidate the next account. Mutations are not automatically replayed.
  A request already received by the server cannot be undone by browser sign-out;
  backend token verification and owner scoping remain authoritative.
- Workspace mounting waits for principal synchronization. Sign-in completion does
  not advance an already-confirmed generation again. Browser regressions caught
  and corrected the premature-profile-request/duplicate-confirmation race instead
  of hiding the profile error or relaxing its assertions.
- Existing V1 behavior, manual mass/provenance, efficiency lookup, gasoline/EV
  models, automatic EIA pricing, price overrides and terrain policy remain intact.
  There is no API schema or migration change.

## Evidence and boundaries

| Scenario | Evidence | Scope |
| --- | --- | --- |
| Real session restore on reload | Existing Neon session loaded profile, saved vehicles and saved preference after reload | Live pinned development environment |
| Real sign-out | Neon SDK sign-out returned to the sign-in form; private workspace removed | Live pinned development environment |
| Real return sign-in | User entered existing credentials directly; profile and saved vehicles returned unchanged, then survived another reload | Live pinned development environment; agent did not handle the password |
| JWT expiry and renewed identity | New `test_m10_session_identity.py` uses production EdDSA verifier, HTTP and real local PostgreSQL; expired token gets 401/Bearer and cannot change preferences/create identity; new JWT for same subject restores the same internal user and exact settings | Offline ephemeral signing key/local JWKS, disposable SQL; no authentication bypass verifier |
| Cross-account isolation | Same integration checks distinct signed subject gets distinct empty profile; existing authorization suites retain owner checks | Offline signed JWT/local PostgreSQL |
| UI expiry, logout/reload/login, second-tab account change | New `v2-session.spec.ts`, desktop Chromium and Pixel 7; profile settings survive return login, expire safely and do not carry to another account | Controlled test-only auth/upstream/storage fixtures, not live Neon multi-account certification |
| Delayed token/response/401 races | `v2Resources.test.ts`; private UI removal, sign-out failure and reauthentication in `V2App.test.tsx`; sign-in callback validation in `AuthPanel.test.tsx` | Unit regressions |
| Registration and verification errors | Existing AuthPanel/auth error/SDK normalization tests | Controlled responses; not proof of email delivery or provider verification policy |

[Sanitized live evidence](validation/m10-development-session.json) stores booleans
and environment classification only. No account IDs, emails, password values,
tokens, private URLs or profile values are published. Real account settings and
vehicles were read, not changed. The existing branch guard verified the private
configuration before startup. No remote schema, auth-provider policy, API key,
allowed-origin setting or EIA cache was changed.

Natural expiration of the real Neon session was not waited for or forced. Expiry
was verified with genuine signed expired JWTs and controlled browser 401s, not by
changing provider TTLs or revoking the user's sessions. The live journey did not
register a new account or reset the user's password.

## Registration/recovery and release policy review

The delivered sign-in method is Neon email/password. Google OAuth remains deferred
as documented in the architecture record. Registration success is not sufficient
to mark the app authenticated: the SDK must expose a session and protected API
requests must verify its JWT. The UI tells users to check their inbox if email
verification is required and never treats an arbitrary provider error as success.

The repository currently has **no password-recovery UI**. Neither private .env
file proves whether verification is mandatory, whether recovery email delivery is
configured, or whether production redirect/origin allowlists are correct. Those
provider/admin policies were not changed or inferred from successful sign-in.
Before public release, review and explicitly resolve:

1. Required email verification and observed verification/recovery email delivery.
2. A supported account-recovery path, including any app reset-password UI and
   allowlisted return URL. SDK method availability alone is not a delivered flow.
3. Hosted HTTPS cookie/browser behavior, allowed origins and callbacks on the
   actual V2 destination. Localhost success is not evidence for a hosted origin.
4. The provider's actual JWT/session lifetimes and revocation expectations. The
   backend verifies signed JWT expiry/issuer using cached JWKS; it does not perform
   session introspection/revocation lookup on every request. Do not promise that
   logout instantly revokes every previously issued bearer JWT before expiry.

These are visible release checks, not features silently treated as delivered by
this batch. Password changes must be completed by the account owner; no passwords
or private mail content should be placed in Git or validation artifacts.

## Files and validation

New: session-boundary module, desktop/mobile session browser suite, signed-token
PostgreSQL/HTTP session integration test, this report and sanitized live evidence.
Updated: V2 app/sign-in callback, authenticated resource requests, client-only
`session_changed` error type, related unit tests and test-only reactive Neon
adapter/Playwright mobile matching. The fake auth adapter is selected exclusively
by the E2E Vite configuration; production imports the real Neon SDK. No files were
deleted. Generated API/TypeScript artifacts regenerate without a committed diff.

The new browser suite initially failed the sign-out/reload/sign-in return journey.
Debugging fixed the session generation ordering. Final frontend typechecking also
caught a misplaced hook argument and missing client-only error type; both were
corrected. All final gates below supersede those failed intermediate runs.

| Gate | Final result |
| --- | --- |
| `uv run ruff check . --fix` | Passed |
| `uv run ruff format .` | Passed |
| `uv run mypy .` | Passed, 316 source files |
| `uv run pytest -q`, designated local databases | **2,260 passed, 1 skipped** |
| `npm run api:generate` | Passed; no public contract/type change |
| `npm run lint` | Passed |
| `npm run format:check` | Passed |
| `npm test -- --run` | **205 passed, 34 files** |
| `npm run build` | Passed, strict TypeScript and Vite |
| `npm run test:e2e` | **20 passed**, including six new desktop/mobile session cases |

The sole backend skip is the opt-in live Google Routes test. No new live terrain
coverage was tested. Existing Starlette/httpx and Playwright color-environment
warnings remain. The full suite includes V1 compatibility, gasoline/EV, optional
mass, automatic pricing/fallback, persisted settings, terrain fairness and quotas.

## Milestone disposition

Implementation and local/Neon-development session acceptance for batch 2 are
complete. Hosted staging is explicitly unavailable by user confirmation; it is
not marked passed. Email verification/recovery delivery and public-release auth
policy remain the release checks above. M10 remains open. Next is batch 3: guarded
shared PostgreSQL terrain accounting activation and operational acceptance, then
EIA refresh/monitor operations and final integrated release review. No production
configuration/deployment, paid service, `main` merge or release tag was performed.
