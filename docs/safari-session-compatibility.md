# Safari session-cache compatibility

## Diagnosis (2026-10-21)

The owner reported that production account loading worked in Chrome but failed in
Safari 16.5. Safari's initial Neon `get-session` request returned HTTP 200 with a
session and the exposed JWT header. No profile API request appeared in the supplied
Network list. These observations do not support cookie blocking as the cause of
this particular failure.

The installed Neon Auth 0.6.0-beta SDK uses static `Response.json()` to construct
cached session responses. That method is absent in Safari 16.5. A regression using
the real SDK with the method removed reproduced a successful initial token read
followed by `TypeError: Response.json is not a function` on the cached read.
RouteValue previously displayed that exception as a generic network failure.

## Change

Before creating the auth client, install a feature-detected implementation of
static `Response.json` using `JSON.stringify`, `Headers` and `new Response`.
Preserve the native method when present. This keeps SDK caching, session
boundaries and bearer-token authentication intact. No cookie policy, credentials,
backend settings or production infrastructure is changed.

## Verification

- API contract/types regenerated successfully using a writable temporary uv cache;
  generated files unchanged.
- Frontend lint, format check, TypeScript and production build passed.
- 271 unit/integration tests passed, including real SDK cached token retrieval
  without static `Response.json`, concurrent reads and compatibility semantics.
- 10 production-bundle browser checks passed on desktop/mobile Chromium. The new
  regression removes static `Response.json` before app startup, uses the real
  Neon SDK with synthetic network responses, verifies JWT-bearing profile,
  preference and vehicle requests, and checks account loading after reload.
- The browser suite needed sandbox escalation to bind its localhost test port.
- Backend source is unchanged; backend tests were not rerun for this frontend fix.

These automated checks emulate the missing API; they are not a test on the owner's
actual Safari or a live production authentication journey. Deployment and an
owner Safari reload/sign-in check remain pending. No copied owner session
credentials are used in test fixtures or saved in this repository.
