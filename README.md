# RouteValue

RouteValue compares driving routes using personalized generalized cost rather than travel time alone.

The V1 application combines:

- travel-time cost based on the user's value of time
- gasoline cost based on route distance, vehicle fuel efficiency, and gas price
- toll cost when available
- deterministic route selection with explicit handling for missing data

The repository contains:

- `backend/` — FastAPI application and RouteValue domain/application logic
- `frontend/` — React + TypeScript + Vite client
- `.github/workflows/ci.yml` — automated CI verification

## Prerequisites

Local development uses:

- Python 3.13
- uv
- Node.js 24
- npm
- Docker Desktop for container verification

## Backend

Install the locked backend environment:

```bash
cd backend
uv sync --locked
```

RouteValue uses a Google Routes API key for live trip evaluation.

To enter the key without echoing it in the terminal:

```bash
read -s "GOOGLE_ROUTES_API_KEY?Google Routes API key: "
export GOOGLE_ROUTES_API_KEY
echo
```

Start the API:

```bash
uv run uvicorn routevalue.main:app --reload
```

The API runs at:

```text
http://127.0.0.1:8000
```

Health check:

```bash
curl -fsS http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

The health endpoint does not require a Google API key.

## Frontend

In a second terminal:

```bash
cd frontend
npm ci
```

The frontend uses a browser-side Google Maps Platform key for Places autocomplete and map rendering.

Enter it without echoing it in the terminal:

```bash
read -s "VITE_GOOGLE_MAPS_API_KEY?Google Maps API key: "
export VITE_GOOGLE_MAPS_API_KEY
echo
```

Start the frontend:

```bash
npm run dev
```

The Vite development server proxies `/api` requests to the local backend at `127.0.0.1:8000`.

## Verification gates

Backend:

```bash
cd backend
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

Frontend:

```bash
cd frontend
npm run api:check
npm test
npm run lint
npm run format:check
npm run build
```

Deterministic browser E2E tests:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

The E2E suite uses deterministic Google Maps / Places fakes and intercepted API responses. It does not require Google API keys or a live backend.

## Backend container

Build the production-style backend image from the repository root:

```bash
docker build -t routevalue-backend:local ./backend
```

Start it without provider credentials for a deterministic health smoke test:

```bash
docker run -d \
  --name routevalue-backend-local \
  -p 8001:8000 \
  routevalue-backend:local
```

Verify the running container:

```bash
curl -fsS http://127.0.0.1:8001/health
```

Expected response:

```json
{"status":"ok"}
```

Clean up:

```bash
docker rm -f routevalue-backend-local
```

For live trip evaluation in a container, provide the Google Routes key at runtime rather than baking it into the image:

```bash
docker run -d \
  --name routevalue-backend-local \
  -p 8001:8000 \
  -e GOOGLE_ROUTES_API_KEY \
  routevalue-backend:local
```

## Continuous integration

GitHub Actions runs automatically on pushes to `main` and pull requests targeting `main`.

The CI workflow independently verifies:

- backend tests, Ruff lint/format, and strict mypy
- OpenAPI contract drift, frontend unit tests, ESLint, Prettier, and production build
- deterministic Playwright browser E2E tests
- backend Docker image build, startup, `/health` smoke test, and cleanup

Ordinary CI does not require Google API credentials.

## Environment configuration

RouteValue uses separate environment variables for local development and production deployment.

### Backend

Live Google Routes requests require:

```text
GOOGLE_ROUTES_API_KEY
```

This is a server-side secret and must never be exposed to the frontend or committed to the repository.

When the production frontend and backend use different origins, configure the allowed frontend origin with:

```text
ROUTEVALUE_CORS_ORIGINS
```

For example:

```text
ROUTEVALUE_CORS_ORIGINS=https://example.pages.dev
```

Multiple explicit origins may be provided as a comma-separated list.

When `ROUTEVALUE_CORS_ORIGINS` is unset, RouteValue does not enable CORS middleware. This is the normal local-development behavior because Vite proxies frontend `/api` requests to the local backend.

### Frontend

The browser-side Google Maps / Places integration uses:

```text
VITE_GOOGLE_MAPS_API_KEY
```

This value is compiled into the frontend bundle and should therefore be treated as browser-visible. Production Google Cloud restrictions should limit it to the appropriate APIs and frontend origins.

The production backend URL is configured with:

```text
VITE_API_BASE_URL
```

When it is unset, the frontend uses:

```text
/api
```

which preserves the existing local Vite proxy workflow.

In production, `VITE_API_BASE_URL` should contain the HTTPS origin of the deployed RouteValue backend.

Do not commit API keys, secrets, or local `.env` files.

Production credentials should be configured through the selected hosting providers' environment-variable and secret-management systems.