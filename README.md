# RouteValue

**Know the cost. Choose what matters.**

RouteValue is a deployed web application that compares driving routes around
**your vehicle, your energy costs and your value of time**. It makes the trade-off
between a faster trip and a cheaper trip explicit, with a personalized cost
breakdown for each eligible route.

The goal is to make everyday driving trade-offs easier to understand: whether
avoiding a toll is worth a longer drive, or whether a faster route justifies
extra energy costs. Users set their own value of time, allowing the recommendation
to reflect their priorities for each trip.

Each comparison separates out-of-pocket spending from the value assigned to
travel time. The result shows both the estimated money spent on the road and the
personalized total used to rank routes, making the reasoning behind a
recommendation visible.

[Architecture decisions](docs/v2-architecture-decisions.md) ·
[Release validation](docs/m11-release-acceptance.md)

![RouteValue trip planner with synthetic demonstration data](docs/design/ui-refresh/desktop-trip.png)

## What you can do

- **Compare the cost of alternative routes.** See estimated gasoline or electricity
  costs, tolls, travel duration and the monetary value of your driving time, with
  route selection on an interactive map.
- **Personalize the recommendation.** Decide what an hour of your time is worth;
  a slower route can win when its savings justify the extra time.
- **Save gasoline and electric vehicles.** Select a vehicle configuration from the
  efficiency catalog, keep multiple vehicles and choose a default.
- **Reuse preferences across sessions.** Save your value of time, electricity rate
  and preferred gasoline purchasing area through authenticated accounts.
- **Choose automatic or manual energy pricing.** Gasoline pricing uses published
  EIA regional observations where supported, with a manual override. EV trips use
  a saved electricity rate or an explicit trip override.
- **Understand terrain estimates and their limits.** Optional, user-entered vehicle
  mass enables terrain-aware energy modeling when usable elevation and route
  geometry are available. Missing prerequisites or unavailable coverage produce
  clearly identified baseline estimates.

The recommendation minimizes:

```text
personalized route cost = energy cost + toll cost + travel time × value of time
```

Money uses decimal arithmetic. Routes without required scoring data are marked
ineligible; missing values are not silently treated as free. Numerical ties use
explicit, deterministic rules.

A saved vehicle provides the efficiency information used in energy estimates,
while persistent preferences carry the user's electricity rate, gasoline
purchasing area and value of time into future comparisons. Users can override
energy prices for a single trip without replacing their saved settings. Route
results show the pricing source and whether terrain adjustments were applied,
so the assumptions behind the comparison remain visible alongside the costs.

## How it is built

A React/TypeScript interface communicates with a Python/FastAPI backend through a
generated OpenAPI contract. The decision engine is independent of HTTP and routing
providers, with explicit application ports and replaceable infrastructure adapters.

```mermaid
flowchart LR
    UI[React + TypeScript] --> API[FastAPI application]
    UI --> MAP[Google Maps and Places]
    API --> DOMAIN[Route normalization and cost decision engine]
    API --> ROUTES[Google Routes]
    API --> ENERGY[Gasoline and EV energy models]
    ENERGY --> TERRAIN[Guarded OpenTopoData acquisition]
    API --> PRICES[EIA pricing snapshots]
    API --> DB[Neon PostgreSQL: profiles, vehicles and preferences]
    UI --> AUTH[Neon Auth]
    AUTH --> API
```

- **Routing and maps:** Google Routes supplies candidates, geometry and available
  toll information; Google Maps and Places support visualization and location entry.
- **Energy:** separate gasoline and EV models, vehicle-efficiency lookup, optional
  manual mass and guarded OpenTopoData elevation acquisition with shared quotas.
- **Persistence and authentication:** Neon PostgreSQL, additive Alembic migrations,
  email/password authentication and JWT-protected, user-owned API resources.
- **Hosting:** Cloudflare Pages frontend, containerized Render backend and isolated
  development/production database and authentication environments.
- **Quality:** pytest, strict mypy and Ruff; Vitest, React Testing Library and
  Playwright; generated API types, production-bundle and container smoke checks.

## Validation and supported scope

The Safari compatibility release (`bc97b72`, October 21, 2026) passed all four CI
jobs on both `v2` and `main`. Its local frontend checks included 271 tests and ten
production-bundle browser checks, including a real-SDK regression for browsers
without static `Response.json`. These are recorded release results, not a claim
that every future provider request or browser version will succeed.

Live release checks covered saved settings, gasoline/EV trips, automatic and
manual pricing, optional manual vehicle mass, and representative US terrain
routes. Terrain acquisition remains dependent on coverage, geometry and quotas.
EIA observations are regional averages, not station-specific or real-time prices.
Google OAuth, Google Elevation and station-level Google gasoline pricing are not
implemented; the [architecture decision record](docs/v2-architecture-decisions.md)
explains these choices.

Production SMTP hardening and longer-running recovery/alert-delivery observations
remain operating follow-ups. See the [release acceptance record](docs/m11-release-acceptance.md)
and [deployment runbook](deployment/README.md) for evidence, limitations and rollback
instructions. Milestone documents describe the state at their recorded dates;
older references to V2 as local-only are historical.

## Repository layout

```text
backend/src/routevalue/
  api/              HTTP schemas, authentication and resource boundaries
  application/      use cases, orchestration and ports
  domain/           units, energy and deterministic cost decisions
  infrastructure/   provider adapters, persistence and operations
frontend/
  src/              application UI and typed API clients
  e2e/              application browser tests
  release-e2e/      production-bundle and real-SDK browser tests
  openapi/          generated backend contract
.github/workflows/  CI and guarded production EIA maintenance
deployment/         production target identifiers and release runbook
docs/               architecture, milestone evidence and design references
```
