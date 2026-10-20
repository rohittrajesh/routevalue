# UI/UX mini-milestone — RouteValue identity and workspace

Date: 2026-10-20. Branch: `v2`.

Status: implementation and local validation complete. The owner approved committing, pushing and deploying the full UI release on 2026-10-20. Publication proceeds through V2 CI and the existing main-branch hosting pipeline. Hosted success requires separate deployment verification. SMTP setup, unattended EIA recovery observations and alert-delivery observations remain paused at the owner's request.

## Goal

Give RouteValue a coherent application identity, reduce oversized typography and the long stack of unrelated forms, and make gasoline-market settings easy to find. Keep existing account, vehicle, preference and trip behavior intact.

## Delivered

- Use a folded-map, route and cost-coin symbol in a violet-to-magenta gradient as the application mark and favicon. Apply dark plum navigation, violet actions, lavender surfaces and restrained magenta accents. No new package, remote font or paid service.
- Replace the oversized landing heading with a compact two-column sign-in screen. Remove duplicate wordmark copy and visible V2 branding, including the loading state.
- Provide Plan a trip, Garage and Preferences navigation. Use a desktop rail and a sticky mobile navigation bar with a clear current-page state.
- Keep the planner and personalization components mounted during view changes, preserving unfinished trip inputs and settings drafts. Existing session-principal boundaries still unmount private state on expiry, sign-out and account changes.
- Provide direct setup shortcuts from the trip view. On mobile, prioritize planner controls over introductory artwork and the redundant account summary.
- Put time and electricity preferences side by side on desktop. Give Preferred fuel market a separate, highlighted section with its own heading, saved-area badge, selection, save and clear controls.
- Put saved vehicles and the add-vehicle form side by side when space allows. Keep optional manual weight, provenance, update/clear actions, deletion confirmation and default-vehicle management.
- Restyle price provenance, recommendations, route cards and terrain status. On wide screens, place the map beside route cost cards rather than adding both to the vertical stack.
- Remove descriptions of backend processing and JavaScript decimal transport from product copy. Keep useful explanations of pricing provenance, baseline fallbacks, optional weight and terrain coverage.
- Keep mutation feedback in the view where the action originated and validation errors next to the relevant settings form. Include focus outlines, native keyboard-operable navigation controls, hidden inactive views, reduced-motion handling and stronger small-text contrast.

## Source and regression changes

New files: `frontend/src/WorkspaceTheme.css`, `frontend/src/components/AppIcon.tsx` and `frontend/public/routevalue-map-cost.svg`. The application mark is also wired into `frontend/index.html`.

Updated app composition and loading copy: `frontend/src/V2App.tsx`, `frontend/src/RouteValueRoot.tsx`.

Updated presentation and copy: `PersonalizationDashboard.tsx`, `EnergyPreferencesEditor.tsx`, `V2TripPlanner.tsx`, `VehicleCatalogPicker.tsx`, `auth/AuthPanel.tsx`, `auth/ResetPasswordPanel.tsx`.

Updated tests: `V2App.test.tsx`, `PersonalizationDashboard.test.tsx`, `V2TripPlanner.test.tsx`, `EnergyPreferencesEditor.test.tsx`, `e2e/v2-workflow.spec.ts`, `e2e/v2-session.spec.ts`, `release-e2e/launch.spec.ts`.

The old lightning-bolt asset `frontend/public/favicon.svg` was removed and replaced by the map-and-cost symbol. No application source files were deleted. No backend logic, migrations, environment files, deployment configuration or dependencies changed. The theme is scoped to V2; V1 source styles remain unchanged. OpenAPI regeneration produced no contract diff.

## Validation actually executed

| Gate | Result |
| --- | --- |
| Backend `uv run ruff check . --fix` | Passed |
| Backend `uv run ruff format .` | 328 files unchanged |
| Backend `uv run mypy .` | Passed, 328 source files |
| Backend `uv run pytest -q` | 2,308 passed, 1 skipped |
| Frontend `npm run api:generate` | Passed, contract unchanged |
| Frontend `npm run lint` | Passed |
| Frontend `npm run format:check` | Passed |
| Frontend `npm test -- --run` | 266 passed across 39 files |
| Frontend `npm run build` | Passed, strict TypeScript and Vite production build |
| Frontend `npm run test:e2e` | 32 passed across desktop Chrome and Pixel 7 emulation |
| Frontend `npm run test:release` | 8 passed across desktop and mobile production-bundle smoke checks |
| `git diff --check` | Passed |

Backend tests used only the designated disposable local PostgreSQL databases `routevalue_m3b4` and `routevalue_m8_eia_test`. The opt-in Google Routes live test was skipped because `RUN_LIVE_GOOGLE_ROUTES` was not enabled. The suite emitted the existing Starlette/httpx deprecation warning.

The browser suite uses synthetic auth, Places, Maps, pricing and terrain acquisitions with the real local API/application calculations. It verifies gasoline automatic/manual pricing, EV persistence/override/clear, preferred-market persistence and origin fallback, manual weight add/clear, terrain/baseline calculations, stale-result invalidation, vehicle deletion/default cleanup, sign-out, expiry, cross-tab isolation and recovery. Navigation regression tests additionally verify hidden views, selected navigation state, preserved drafts and no horizontal overflow. Result-invalidation assertions return to the trip view before checking results, so hiding the planner cannot satisfy those checks.

A read-only check of the running local app also confirmed the redesigned UI loads with the owner's existing development session and saved vehicles. No owner data was changed for design validation.

## Visual evidence

The images below use synthetic browser-test data, not owner account details. The map test double does not draw Google map tiles; its blank canvas is not evidence of a live map failure or of successful live map rendering.

- [Desktop trip workspace](design/ui-refresh/desktop-trip.png)
- [Desktop garage](design/ui-refresh/desktop-garage.png)
- [Desktop settings](design/ui-refresh/desktop-settings.png)
- [Desktop sign-in](design/ui-refresh/desktop-sign-in.png)
- [Mobile trip workspace](design/ui-refresh/mobile-trip.png)
- [Mobile settings](design/ui-refresh/mobile-settings.png)
- [Mobile sign-in](design/ui-refresh/mobile-sign-in.png)
- [Desktop route results](design/ui-refresh/desktop-results.png)
- [Mobile route results](design/ui-refresh/mobile-results.png)

## Release limits

At the local-review checkpoint, this batch was available at `http://localhost:5173/v2`; the owner subsequently approved publication. The local checks below do not independently prove a GitHub CI outcome, hosted deployment or new live Google Routes/OpenTopoData coverage test. Live map tiles, terrain availability, provider quotas and email delivery were not newly validated by this UI batch. Existing honest fallback and provenance behavior remain in place. Browser automation covered Chromium desktop/mobile; Safari and Firefox were not exercised.

## Owner refinement pass — 2026-10-20

- Replaced the generic travel headline with “Know the cost. Choose what matters.” Supporting copy describes personalized energy, toll and travel-time costs, including when a longer drive could cost less.
- Replaced the lightning bolt with an original branching-route R mark. A distinct asset URL prevents the previous logo from remaining cached in the local preview.
- Renamed the visible navigation and related planner instructions to Preferences. Internal view identifiers and saved-data contracts remain unchanged.
- Applied a quieter violet tint and border to the main cards, account summary and quick actions, retaining clear white inputs and distinct error/success colors.
- Top-aligned the workspace so loading/error states do not float in the middle of a tall blank page.
- Repeated the frontend lint, format, unit, build and desktop/mobile browser gates. The Python/backend checks above were executed during the initial UI pass; they were not repeated for this copy/style/asset refinement, which changes no backend files.

Profile-error investigation: the local backend `/health` returned 200, the unauthenticated frontend profile proxy returned the expected 401, and the existing authenticated development session loaded its profile and vehicles in the browser. The screenshot's different-session failure was not reproduced; this does not establish its original cause or prove that all accounts can load. No credential, authentication-provider or production configuration was changed.

## Map-and-cost identity and final polish — 2026-10-20

Replaced the rejected R concept with a folded map, a route between endpoints and a cost coin, without using another provider's pin silhouette. The application mark and favicon share `routevalue-map-cost.svg`; the earlier R asset was removed. The map symbol is also used for the trip navigation icon. Removed the repeated mark from the sidebar footer.

Reduced the desktop trip banner to a concise summary so the planner sits higher on the page. Long account emails now truncate visually with the complete address available on hover and to assistive technology. The fuel-market form explains why saving is disabled until a suggestion is selected, then confirms the selection is ready to save. Existing disabled-state safeguards remain intact.

Profile loading now distinguishes network failures from temporary service failures while retaining Retry profile and protecting upstream details. Two added regressions verify those messages. This is a messaging improvement, not a claim that the earlier owner's profile failure was diagnosed or fixed.

Repeated frontend lint, format check, strict production build, 256 unit tests, 32 desktop/mobile workflow tests and 8 production-bundle smoke checks. No backend, authentication provider, database, credential or production configuration changes were made. At this refinement checkpoint, the working-tree changes were uncommitted and undeployed.

[Map-and-cost symbol preview](design/ui-refresh/map-cost-logo.png)

## Address selection duplication regression — 2026-10-20

The Places adapter previously concatenated `displayName` and `formattedAddress` unconditionally. For a street-address place, the name can already be the leading part of the full address, producing a repeated street address after selection.

The adapter now uses the formatted address once when it already contains the complete name at a comma-delimited prefix boundary, or equals it. Case, whitespace and comma spacing are normalized only for the comparison; the provider's original address is retained for display. Distinct business/landmark names are still included. Coordinates, place identifiers, requested SDK fields and session handling are unchanged. The shared fix applies to origin, destination and fuel purchasing area inputs, including V1's shared address picker.

Added seven provider-formatting cases and three component/adapter integration regressions using the real Places adapter with a synthetic Google SDK. They cover mouse and keyboard selection, replacing partial input, resolved selection state, full address/coordinate/identifier propagation, duplicate full-name handling, formatting variations, missing name/address and preservation of distinct or partial-prefix business names. Six assertions failed before the fix; all 14 targeted tests passed afterward.

Validation for this fix: frontend API regeneration (no contract diff), lint, format check, 266 tests across 39 files, strict TypeScript/Vite build, 32 desktop/mobile workflow tests and 8 production-bundle checks. No Python or backend files changed; backend gates were not rerun for this frontend-only fix. External Places responses in regressions were synthetic; no claim of a new live Google Places test is made. No owner address was stored in fixtures or documentation. No commit, push or deployment was performed at this address-fix checkpoint; the owner subsequently approved the full release.

Changed files: `frontend/src/integrations/googlePlaces.ts`, `frontend/src/integrations/googlePlaces.test.ts`, new `frontend/src/components/PlaceAutocompleteInput.googlePlaces.test.tsx`, and this record.
