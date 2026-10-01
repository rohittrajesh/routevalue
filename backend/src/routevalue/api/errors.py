"""Public API error handling for RouteValue."""

from fastapi import Request
from fastapi.responses import JSONResponse

from routevalue.infrastructure.routing.google_routes import (
    GoogleRoutesError,
    GoogleRoutesHTTPError,
    GoogleRoutesResponseError,
    GoogleRoutesTransportError,
)


def google_routes_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Translate Google Routes infrastructure failures into stable HTTP errors."""

    del request

    if not isinstance(exc, GoogleRoutesError):
        raise TypeError("expected GoogleRoutesError")

    if isinstance(exc, GoogleRoutesTransportError):
        return JSONResponse(
            status_code=503,
            content={
                "detail": "routing provider unavailable",
            },
        )

    if isinstance(exc, GoogleRoutesHTTPError):
        if exc.status_code == 429 or 500 <= exc.status_code <= 599:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "routing provider unavailable",
                },
            )

        return JSONResponse(
            status_code=502,
            content={
                "detail": "routing provider request failed",
            },
        )

    if isinstance(exc, GoogleRoutesResponseError):
        return JSONResponse(
            status_code=502,
            content={
                "detail": "routing provider returned an invalid response",
            },
        )

    return JSONResponse(
        status_code=502,
        content={
            "detail": "routing provider failed",
        },
    )
