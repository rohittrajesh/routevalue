# M10 final integration acceptance

Based on `b38c89d` on branch `v2`. This record supersedes the remaining-work
lists in earlier batch reports; those reports retain their historical results.
The user selected the local application and pinned Neon development branch because
there is no hosted V2 staging deployment. No production deployment is certified.

## Final implementation batch: account recovery

The original final batch implemented link recovery but missed this development
branch's code-based email verification. Owner acceptance exposed the missing code
entry. The follow-up adds distinct code verification and password-reset workflows
through the existing real Neon Better Auth React adapter. Signup and unverified
sign-in lead to verification code entry; existing codes can be entered without
sending another email. Verification confirms email ownership and may establish a
provider session; it never calls the password-reset endpoint.

“Forgot password?” now requests an OTP with `emailOtp.requestPasswordReset`.
The next step requires the email code, a new password and confirmation, and calls
`emailOtp.resetPassword`. Existing reset codes are also supported. Success clears
secret inputs, invalidates the private workspace boundary and attempts sign-out;
a sign-out retry cannot replay the reset. Wrong/expired codes clear secret inputs
and allow an explicit resend. Email edits clear codes/passwords; email validation
also runs before code submission. Requests/submissions/back navigation are disabled
while pending. Codes/passwords remain in component memory, outside URLs/storage.

Email-only modes discard any previously entered sign-in password. Unknown-account
responses use the same eligibility notice as accepted requests; provider error
details, addresses and codes are never rendered as error text. Explicit false
success/status responses cannot be mistaken for success. Rate limits and
availability failures remain retryable, safe failures. No automatic email resend,
provider policy change or code/password submission on behalf of the owner occurs.

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
The distinct OTP endpoints were checked against the installed client and
[Better Auth email OTP documentation](https://better-auth.com/docs/plugins/email-otp).
Neon's [managed email documentation](https://github.com/neondatabase/website/blob/main/content/docs/auth/guides/customize-emails.md)
describes provider email delivery. These establish interfaces, not successful
inbox delivery by themselves. The owner subsequently confirmed verification-email
delivery, code acceptance and sign-in on October 20. The owner subsequently reported that password reset fully works. This is owner
acceptance of the recovery path, not an agent-observed credentials test; sign-in
with the changed password was not separately described step by step. The
Neon management policy has not been changed. The retained link reset screen also
remains covered; hosted policy/origins must be validated for the release target.

## Consolidated disposition

| Capability | Final evidence | Disposition |
| --- | --- | --- |
| Auth identity, ownership, profiles and session boundaries | Batch 2 live restore/sign-out/user-completed sign-in; signed JWT/local PostgreSQL integration; expiry, late response and account-switch regressions | Implemented and tested in the selected development scope |
| Preference consistency and persistence | Batch 1 real SQL interleavings; browser reload, zero/unset/clear, saved EV rate and market-origin fallback journeys | Implemented and tested |
| Optional manual mass and provenance | Manual add/update/clear and persistence regressions; browser journeys | Implemented and tested; automatic weight registry remains removed |
| Gasoline and EV decisions | Backend domain/API suites, exact money/tie regressions and integrated browser workflows | Implemented and tested |
| Automatic EIA pricing and override | Batch 4 actual regional downloads and six real grade resolutions; final read-only freshness and job checks | Implemented and healthy at recorded check time |
| Shared terrain accounting and truthful fallback | Batch 3 bounded real CA/CO/NC routes, restart/lock failure evidence; final read-only shared-ledger health | Implemented and tested for representative routes; no universal coverage claim |
| Recovery requests, reset screen and safe failures | Real SDK link/OTP HTTP contract interception, unit and desktop/mobile browser tests; actual Neon invalid-body OTP and random invalid-token rejection | Implementation complete; owner reports real password reset fully working; agent did not handle credentials |
| Registration and verification | Prior development account/sign-in; owner-reported verification email delivery, code acceptance and sign-in; signup/unverified-sign-in code regressions | Development verification confirmed by owner; hosted policy remains a release check |
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
| `npm test -- --run` | 234 passed, 37 files |
| `npm run build` | Passed, strict TypeScript and production bundling |
| `npm run test:e2e` | 30 passed, desktop and mobile Chromium, test-only identity/provider fixtures |

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

All identified remaining M10 code is implemented and the owner reports that
password reset fully works. Earlier owner feedback confirmed verification-code
acceptance and sign-in, followed by a failed repeat verification attempt. The
specific reason for that later rejection was not captured and is not asserted to
be expiry or an already-verified account.

At the owner's request, the unnecessary general verification action was removed
from ordinary sign-in. Verification remains available only through signup or an
explicit unverified-email rejection from Neon; provider security requirements
were not disabled. The SDK's normalization of unknown OTP errors into
`validation_failed` was reproduced through the real installed client. Those
rejections now receive actionable code feedback; known already-verified responses
point back to sign-in. The new regression tests cover both cases without exposing
raw provider text or treating arbitrary failures as successful verification.

This finishes the selected local development recovery implementation and owner
reset check. It does not certify every provider policy or declare production
launch readiness. Required verification for genuinely new/unverified accounts,
new-password sign-in and exact hosted callbacks remain explicit release acceptance
checks; a repeat optional verification failure is not proof that those checks
passed. No owner code/password was submitted by the agent, copied into tests,
documentation, commits or provider probes.

Empty invalid-body live probes returned 400 from `email-otp/verify-email`,
`email-otp/request-password-reset` and `email-otp/reset-password`; the older
`email-otp/passcode` entry in the SDK's server endpoint map returned 404. The real
installed React client maps the currently supported methods to the modern paths,
verified by intercepted transport tests. These live probes sent no email or code
and changed no account. [Follow-up evidence](validation/m10-email-code-acceptance.json)
keeps owner-observed verification distinct from unverified real password reset.

The implementation is ready for M11 deployment planning within these evidence
limits. Hosted end-to-end authentication and provider-policy acceptance must not
be inferred from this local reset result. M11 must explicitly provide and validate:

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

Changed files across the final batch and follow-up add reset/link and email-code
screens, a safe shared result helper, SDK contract and recovery regressions/browser
journeys; extend auth panel/errors and the test-only Neon fixture; and update V2
routing, architecture and this acceptance record.
No files were deleted. All tracked changes are in the user's RouteValue project
folder and visible in VS Code; private environment/runtime files remain ignored.
