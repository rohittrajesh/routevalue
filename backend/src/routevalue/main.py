"""FastAPI entry point for RouteValue."""

from fastapi import FastAPI

from routevalue.api.routes import router

app = FastAPI(
    title="RouteValue API",
)
app.include_router(router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Report whether the RouteValue API process is available."""
    return {"status": "ok"}
