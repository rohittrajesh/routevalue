# M10 final integration acceptance

Based on `b38c89d` on branch `v2`. This record supersedes the remaining-work
lists in earlier batch reports; those reports retain their historical results.
The user selected the local application and pinned Neon development branch because
there is no hosted V2 staging deployment. No production deployment is certified.

## Final implementation batch: account recovery

The sign-in panel now offers password-reset requests and verification-email
resends through the existing real Neon Better Auth React adapter. Both callbacks
are fixed to the current app origin and V2 routes; there is no user-supplied
redirect destination. Email-only modes discard any previously entered password.
Unknown-account responses use the same eligibility notice as accepted requests;
provider error details, addresses and tokens are never rendered as error text.
Rate limits and availability failures remain retryable, safe failures.

`/v2/reset-password` is a distinct lazy-loaded V2 screen. It accepts a single,
bounded token, rejects missing/duplicate/error-bearing links and removes the
query/fragment from the current history entry after capture. The token stays only
in component memory: a reload requires reopening the original email link. It is
not stored, rendered, logged or passed to application APIs. Matching passwords
with browser length validation are submitted directly to the real auth SDK.
Passwords are cleared after a response. Successful reset requires fresh sign-in:
the old private workspace boundary is invalidated and SDK sign-out is attempted.
If sign-out fails, an explicit retry cannot replay the completed password reset.
This does not claim instant revocation of every already-issued backend JWT.

Existing `/v2` authentication and V1 routing remain intact. There is no new
application API, migration, dependency, authentication bypass or provider-policy
change. The reset route must be included in the eventual host's SPA fallback.

The SDK methods and reset-link contract were checked against the installed
package and [Better Auth email/password documentation](https://better-auth.com/docs/authentication/email-password).
Neon's [managed email documentation](https://github.com/neondatabase/website/blob/main/content/docs/auth/guides/customize-emails.md)
describes provider email delivery. These establish interfaces, not successful
inbox delivery for this branch. Link-versus-OTP verification policy has not been
read from the Neon management API or changed. The app implements link recovery;
a provider requiring an alternative flow must be validated before release.

## Consolidated disposition

| Capability | Final evidence | Disposition |
| --- | --- | --- |
| Auth identity, ownership, profiles and session boundaries | Batch 2 live restore/sign-out/user-completed sign-in; signed JWT/local PostgreSQL integration; expiry, late response and account-switch regressions | Implemented and tested in the selected development scope |
| Preference consistency and persistence | Batch 1 real SQL interleavings; browser reload, zero/unset/clear, saved EV rate and market-origin fallback journeys | Implemented and tested |
| Optional manual mass and provenance | Manual add/update/clear and persistence regressions; browser journeys | Implemented and tested; automatic weight registry remains removed |
| Gasoline and EV decisions | Backend domain/API suites, exact money/tie regressions and integrated browser workflows | Implemented and tested |
| Automatic EIA pricing and override | Batch 4 actual regional downloads and six real grade resolutions; final read-only freshness and job checks | Implemented and healthy at recorded check time |
| Shared terrain accounting and truthful fallback | Batch 3 bounded real CA/CO/NC routes, restart/lock failure evidence; final read-only shared-ledger health | Implemented and tested for representative routes; no universal coverage claim |
| Recovery requests, reset screen and safe failures | Real SDK HTTP contract interception, unit and desktop/mobile browser tests; actual Neon random invalid-token rejection | Implementation complete; real inbox/reset/return-sign-in owner acceptance pending |
| Registration and verification | Prior user-created development account and real sign-in; resend UI/SDK contract tests | Existing registration works for that account; new verification-email delivery/policy acceptance pending |
| V1 compatibility, schema and CI gates | Full backend suite, V1 browser journeys, generated contract drift check and strict production build | Passed locally; exact pushed commit CI tracked separately |
| Provider scope | `v2-architecture-decisions.md` reconciles original freeze | Google Routes/OpenTopoData/EIA/Neon email-password supported; Google Elevation, station-price aggregation and Google OAuth deferred |
| Hosted HTTPS staging, production rollout and operations | No V2 hosted target exists | M11 provisioning/release gates, explicitly unverified |

## Executed final checks

| Gate | Result |
| --- | --- |
| `uv run ruff check . --fix` | Passed |
| `uv run ruff format .` | Passed, 322 files unchanged |
| `uv run mypy .` | Passed, 322 source files |
| `uv run pytest -q`, designated disposable PostgreSQL databases only | 2,291 passed, 1 skipped |
| `npm run api:generate` | Passed; no generated contract/type diff |
| `npm run lint` | Passed |
| `npm run format:check` | Passed after correcting formatting in the new SDK contract test |
| `npm test -- --run` | 220 passed, 36 files |
| `npm run build` | Passed, strict TypeScript and production bundling |
| `npm run test:e2e` | 26 passed, desktop and mobile Chromium, test-only identity/provider fixtures |

The sole backend skip is the existing opt-in live Google Routes test, not a passed
test. Live route evidence from batch 3 is separate and was not rerun in this final
batch. Existing Starlette/httpx and browser color warnings remain. Initial reset
screen typechecking caught the SDK's required sign-out argument; the corrected
`signOut({})` passes the production TypeScript build. No assertion was weakened.

On October 20, 2026 at approximately 21:06 UTC, read-only development checks showed:

- Both EIA regions healthy for all three grades, with October 19 source observations.
- The local hourly job registered, latest execution healthy, last exit code zero.
- Shared terrain mode ready: 900 rolling-day limit, six calls/trip, 1.1-second
  reservation spacing, 18 active reservations and 882 remaining. These checks made
  no provider requests or quota writes.
- A random unrelated reset token was rejected by the real configured Neon service
  with HTTP 400 and `INVALID_TOKEN`. No email was requested or real password used.
  This verifies a rejection path, not a successful reset or email delivery.
  [Sanitized endpoint evidence](validation/m10-recovery-endpoint.json) records that boundary.

## Closure and M11 handoff

All identified remaining M10 code is implemented. **M10 acceptance remains open
only for owner-observed development recovery/verification delivery and the return
sign-in journey.** The owner was asked to exercise the finished UI without sharing
credentials or reset links. Automated transport/browser fixtures cannot certify
that provider policy or mailbox journey. No unattended email or account mutation
was performed to manufacture acceptance.

Once that check passes, the local/pinned-development M10 scope can close and M11
can begin. Until then, do not label all M10 acceptance complete or claim launch
readiness. M11 must explicitly provide and validate:

1. An approved hosted V2 target, HTTPS auth origins/callbacks/cookies and SPA routes,
   including direct reset-link navigation, with provider verification/reset policy.
2. Runtime secrets, schema compatibility and shared terrain policy on every worker;
   rollback and V1 isolation before any approved release migration/deployment.
3. Hosted EIA scheduling with shared retry state, operator ownership, real alert
   delivery, and observation of unattended weekly recovery. The Mac job requires
   this workspace/login/network and cannot provide an always-on service.
4. Exact-release live gasoline/EV, pricing and representative terrain smoke tests,
   plus desktop/mobile account journeys, documented budget/usage checks and rollback.
5. Explicit approval for production changes, `main` merge/deploy and release tagging.

No paid service, hosted staging, production config change, migration or `main`
merge is included. Terrain quality/availability remains route-dependent; the
six-call budget is an allowance, not proof of universal coverage or a paid SLA.

Changed files add the reset screen, safe shared result helper, SDK contract and
recovery regressions/browser journeys; extend auth panel/errors and the test-only
Neon fixture; and update V2 routing, architecture and this acceptance record.
No files were deleted. All tracked changes are in the user's RouteValue project
folder and visible in VS Code; private environment/runtime files remain ignored.
