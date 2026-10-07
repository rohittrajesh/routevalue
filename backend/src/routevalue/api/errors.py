"""Public API error handling for RouteValue."""

from fastapi import Request
from fastapi.responses import JSONResponse

from routevalue.api.schemas import ApiErrorCode
from routevalue.infrastructure.routing.google_routes import (
    GoogleRoutesError,
    GoogleRoutesHTTPError,
    GoogleRoutesResponseError,
    GoogleRoutesTransportError,
)


class ServiceConfigurationError(RuntimeError):
    """Raised when required server-side RouteValue configuration is unavailable."""


class AuthenticationRequiredError(RuntimeError):
    """Raised when an API request lacks acceptable authentication."""


class AuthenticationServiceUnavailableError(RuntimeError):
    """Raised when authentication cannot be verified due to provider availability."""


def _api_error_response(
    *,
    status_code: int,
    code: ApiErrorCode,
    detail: str,
) -> JSONResponse:
    """Build one stable RouteValue API error response."""

    return JSONResponse(
        status_code=status_code,
        content={
            "code": code.value,
            "detail": detail,
        },
    )


def authentication_required_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Return the stable response for missing or invalid authentication."""

    del request

    if not isinstance(exc, AuthenticationRequiredError):
        raise TypeError("expected AuthenticationRequiredError")

    response = _api_error_response(
        status_code=401,
        code=ApiErrorCode.AUTHENTICATION_REQUIRED,
        detail="Authentication is required.",
    )

    response.headers["WWW-Authenticate"] = "Bearer"

    return response


def authentication_service_unavailable_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Return the stable response when authentication verification is unavailable."""

    del request

    if not isinstance(exc, AuthenticationServiceUnavailableError):
        raise TypeError("expected AuthenticationServiceUnavailableError")

    return _api_error_response(
        status_code=503,
        code=ApiErrorCode.AUTHENTICATION_SERVICE_UNAVAILABLE,
        detail="Authentication is temporarily unavailable. Please try again.",
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
        return _api_error_response(
            status_code=503,
            code=ApiErrorCode.ROUTING_SERVICE_UNAVAILABLE,
            detail="Routes are temporarily unavailable. Please try again.",
        )

    if isinstance(exc, GoogleRoutesHTTPError):
        if exc.status_code == 429 or 500 <= exc.status_code <= 599:
            return _api_error_response(
                status_code=503,
                code=ApiErrorCode.ROUTING_SERVICE_UNAVAILABLE,
                detail="Routes are temporarily unavailable. Please try again.",
            )

        return _api_error_response(
            status_code=502,
            code=ApiErrorCode.ROUTING_SERVICE_ERROR,
            detail="The routing service could not complete this request.",
        )

    if isinstance(exc, GoogleRoutesResponseError):
        return _api_error_response(
            status_code=502,
            code=ApiErrorCode.ROUTING_RESPONSE_INVALID,
            detail="The routing service returned an invalid response. Please try again.",
        )

    return _api_error_response(
        status_code=502,
        code=ApiErrorCode.ROUTING_SERVICE_ERROR,
        detail="The routing service could not complete this request.",
    )


def service_configuration_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Translate known server configuration failures into a safe public response."""

    del request

    if not isinstance(exc, ServiceConfigurationError):
        raise TypeError("expected ServiceConfigurationError")

    return _api_error_response(
        status_code=500,
        code=ApiErrorCode.SERVICE_CONFIGURATION_ERROR,
        detail="RouteValue is temporarily unavailable. Please try again later.",
    )
