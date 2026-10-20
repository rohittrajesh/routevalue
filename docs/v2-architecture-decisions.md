# V2 implementation decisions and original-plan reconciliation

This record supplements the supplied V2 vision and M0 architecture freeze. It
distinguishes implemented behavior from original provider plans. It does not
rewrite the original documents or claim that deferred integrations have shipped.

## Product and dependency direction

The V2 product remains authenticated, vehicle-aware monetary route comparison for
gasoline and battery-electric vehicles. Generalized cost is energy cost plus tolls
plus travel time valued using the saved preference. Distance is an energy-model
input, not an additional penalty. Decimal money, distinct physical energy types,
the existing numerical tie/tie-break rules and V1 compatibility remain unchanged.

Dependencies remain API → application/use cases → ports/domain, with replaceable
infrastructure adapters. Frontend business data flows through authenticated API
resources, never direct writes to RouteValue tables. Saved vehicles are owned
snapshots; catalog efficiency lookup is preserved. Weight is optional, owner-entered
only, with provenance, validation and add/update/clear. No automatic manufacturer
registry, automatic weight resolution or guessed mass is part of this release.

## Original providers versus the implemented workflow

| Original M0 plan | Implemented workflow | Explicit disposition |
| --- | --- | --- |
| Google Elevation API | Google Routes HIGH_QUALITY geometry plus guarded public OpenTopoData `ned10m` acquisition | OpenTopoData is the current terrain adapter. Google Elevation is not implemented/enabled. A future switch requires a separate integration, verified account quotas/cost controls and validation; the user's $10/month ceiling is not permission for uncapped billing. |
| Google Places `fuelOptions`, nearest valid station median, EIA fallback | Persisted EIA California/national observations, trusted geographic resolution, observation-aware freshness and manual override | EIA is the implemented automatic regional service. Station-level Google pricing and its aggregation workflow are not delivered. Retain as deferred provider enhancement/scope review, not a hidden dependency of the working EIA path. Places autocomplete for routing/settings is separate from station fuel-price acquisition. |
| Google OAuth as initial login | Real Neon Managed Better Auth email/password registration/sign-in and authenticated JWT API access | Email/password is the implemented authentication UI. Google OAuth is not delivered and must not be advertised. Retain as a deferred sign-in-method decision/integration; real Neon authentication is not mocked in the product. |

These provider-specific deviations are explicitly recorded in response to the
requested reconciliation. Closing the implemented M9 workflow does not certify
those original provider integrations. Before M11 release, review the supported
provider/authentication scope and ensure public descriptions match it. No paid
services or production configuration were enabled by this reconciliation.

## Completed preference behavior

- `electricity_price_per_kwh` is an optional persisted user preference, shared
  across that user's EVs. It is a finite nonnegative Decimal; zero is valid and
  unset is distinct from zero. No utility rate or economic default is invented.
- Normal EV requests omit electricity pricing and use the server-resolved saved
  rate. Explicit trip electricity input overrides it without changing storage.
  If neither exists, the API returns `electricity_price_not_configured`; the UI
  points to personal settings or the explicit trip override. Gasoline inputs
  remain invalid for EVs, including when a saved electricity rate exists.
- Price provenance distinguishes `user_preference` from `user_input`. UI labels
  accurately identify the saved rate versus the trip override. The saved input
  retains its exact decimal representation; calculations do not round it to cents.
- `preferred_fuel_market` is an optional user-selected purchasing area represented
  by display name and coordinates. No home address is required. Provider IDs,
  station prices and a browser-supplied EIA region are not stored in this field.
  It changes the pricing reference, never the trip origin or route search.
- Automatic gasoline pricing uses saved market coordinates when present, otherwise
  trip origin. The server's trusted Census/jurisdiction resolver selects the EIA
  geography; a display name cannot impersonate a different state. Unsupported
  saved areas fail honestly rather than silently pricing elsewhere. The user can
  clear the market to restore origin pricing or use a manual gasoline override.
- Omitted PATCH fields remain unchanged; explicit null clears only that preference.
  Ownership validation and default-vehicle deletion preserve unrelated preferences.

## Terrain and pricing invariants

All candidates in a comparison use a consistent energy-model tier. Missing manual
mass, inadequate geometry/coverage, acquisition failure or exhausted quotas lead
to shared baseline estimates and truthful `terrain_status`. Raster coverage does
not establish road-grade accuracy or universal availability. Gasoline and EV
terrain calculations retain their separate models.

The live terrain allowance is six calls/trip, with existing 100-point batches,
900 calls per rolling day and 1.1-second spacing. Process mode is development-only.
PostgreSQL accounting supports shared workers/restarts but must be migrated and
enabled consistently before deployment. Failed attempts are counted. There is no
automatic switch to unmetered access when accounting fails.

Trip evaluation reads EIA snapshots; it never refreshes them. Refresh operations
preserve source observation dates. The read-only health monitor uses the same
publication-aware expiry policy as the resolver. Production scheduling/monitoring
provisioning remains deployment work.

## Milestone boundaries

- **M9:** complete the implemented authenticated desktop/mobile workflow: vehicle
  setup/defaults, persistent value of time/electricity rate/fuel market, gasoline
  and EV evaluation, optional manual mass, pricing provenance, terrain/fallback
  explanations and usable recovery states. The final preference batch closes the
  identified UI/product gaps when its validation passes.
- **M10:** integrated hardening and acceptance review, real session lifecycle and
  staging checks, shared quota activation, refresh/monitor operations, recovery,
  cost controls and confirmation of the supported release scope above.
- **M11:** approved production migrations/configuration, exact-commit live gasoline,
  EV, terrain and pricing smoke tests, desktop/mobile checks, rollback verification,
  then explicit approval to merge/deploy/tag `v2.0.0`.

V1 production stays on `main`; development stays on `v2`. Tests and a working local
app are evidence for M9/M10, not proof of production deployment or a completed M11.
