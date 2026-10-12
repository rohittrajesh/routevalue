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
from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FuelEconomyGovError,
    FuelEconomyGovHTTPError,
    FuelEconomyGovResponseError,
    FuelEconomyGovTransportError,
)


class ServiceConfigurationError(RuntimeError):
    """Raised when required server-side RouteValue configuration is unavailable."""


class AuthenticationRequiredError(RuntimeError):
    """Raised when an API request lacks acceptable authentication."""


class AuthenticationServiceUnavailableError(RuntimeError):
    """Raised when authentication cannot be verified due to provider availability."""


class SavedVehicleNotFoundError(RuntimeError):
    """Raised when an owned saved vehicle cannot be found."""


class VehicleConfigurationNotFoundError(RuntimeError):
    """Raised when a selected catalog configuration no longer exists."""


class VehicleSpecificationUnavailableError(RuntimeError):
    """Raised when a configuration cannot yield a supported specification."""


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

    if not isinstance(
        exc,
        AuthenticationRequiredError,
    ):
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

    if not isinstance(
        exc,
        AuthenticationServiceUnavailableError,
    ):
        raise TypeError("expected AuthenticationServiceUnavailableError")

    return _api_error_response(
        status_code=503,
        code=(ApiErrorCode.AUTHENTICATION_SERVICE_UNAVAILABLE),
        detail=("Authentication is temporarily unavailable. Please try again."),
    )


def saved_vehicle_not_found_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Hide whether a saved vehicle exists outside the caller's ownership scope."""

    del request

    if not isinstance(
        exc,
        SavedVehicleNotFoundError,
    ):
        raise TypeError("expected SavedVehicleNotFoundError")

    return _api_error_response(
        status_code=404,
        code=ApiErrorCode.SAVED_VEHICLE_NOT_FOUND,
        detail="Saved vehicle was not found.",
    )


def vehicle_configuration_not_found_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Return the stable response for a stale or invalid catalog selection."""

    del request

    if not isinstance(
        exc,
        VehicleConfigurationNotFoundError,
    ):
        raise TypeError("expected VehicleConfigurationNotFoundError")

    return _api_error_response(
        status_code=404,
        code=(ApiErrorCode.VEHICLE_CONFIGURATION_NOT_FOUND),
        detail=("The selected vehicle configuration could not be found."),
    )


def vehicle_specification_unavailable_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Return the stable response for unsupported vehicle specification data."""

    del request

    if not isinstance(
        exc,
        VehicleSpecificationUnavailableError,
    ):
        raise TypeError("expected VehicleSpecificationUnavailableError")

    return _api_error_response(
        status_code=409,
        code=(ApiErrorCode.VEHICLE_SPECIFICATION_UNAVAILABLE),
        detail=("The selected vehicle does not have a supported energy specification."),
    )


def fuel_economy_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Translate FuelEconomy.gov failures into stable public API errors."""

    del request

    if not isinstance(
        exc,
        FuelEconomyGovError,
    ):
        raise TypeError("expected FuelEconomyGovError")

    if isinstance(
        exc,
        FuelEconomyGovTransportError,
    ):
        return _api_error_response(
            status_code=503,
            code=(ApiErrorCode.VEHICLE_CATALOG_SERVICE_UNAVAILABLE),
            detail=("Vehicle data is temporarily unavailable. Please try again."),
        )

    if isinstance(
        exc,
        FuelEconomyGovHTTPError,
    ):
        if exc.status_code == 429 or 500 <= exc.status_code <= 599:
            return _api_error_response(
                status_code=503,
                code=(ApiErrorCode.VEHICLE_CATALOG_SERVICE_UNAVAILABLE),
                detail=("Vehicle data is temporarily unavailable. Please try again."),
            )

        return _api_error_response(
            status_code=502,
            code=(ApiErrorCode.VEHICLE_CATALOG_SERVICE_ERROR),
            detail=("The vehicle data service could not complete this request."),
        )

    if isinstance(
        exc,
        FuelEconomyGovResponseError,
    ):
        return _api_error_response(
            status_code=502,
            code=(ApiErrorCode.VEHICLE_CATALOG_RESPONSE_INVALID),
            detail=("The vehicle data service returned an invalid response. Please try again."),
        )

    return _api_error_response(
        status_code=502,
        code=(ApiErrorCode.VEHICLE_CATALOG_SERVICE_ERROR),
        detail=("The vehicle data service could not complete this request."),
    )


def google_routes_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Translate Google Routes infrastructure failures into stable HTTP errors."""

    del request

    if not isinstance(
        exc,
        GoogleRoutesError,
    ):
        raise TypeError("expected GoogleRoutesError")

    if isinstance(
        exc,
        GoogleRoutesTransportError,
    ):
        return _api_error_response(
            status_code=503,
            code=(ApiErrorCode.ROUTING_SERVICE_UNAVAILABLE),
            detail=("Routes are temporarily unavailable. Please try again."),
        )

    if isinstance(
        exc,
        GoogleRoutesHTTPError,
    ):
        if exc.status_code == 429 or 500 <= exc.status_code <= 599:
            return _api_error_response(
                status_code=503,
                code=(ApiErrorCode.ROUTING_SERVICE_UNAVAILABLE),
                detail=("Routes are temporarily unavailable. Please try again."),
            )

        return _api_error_response(
            status_code=502,
            code=(ApiErrorCode.ROUTING_SERVICE_ERROR),
            detail=("The routing service could not complete this request."),
        )

    if isinstance(
        exc,
        GoogleRoutesResponseError,
    ):
        return _api_error_response(
            status_code=502,
            code=(ApiErrorCode.ROUTING_RESPONSE_INVALID),
            detail=("The routing service returned an invalid response. Please try again."),
        )

    return _api_error_response(
        status_code=502,
        code=ApiErrorCode.ROUTING_SERVICE_ERROR,
        detail=("The routing service could not complete this request."),
    )


def service_configuration_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Translate known server configuration failures into a safe public response."""

    del request

    if not isinstance(
        exc,
        ServiceConfigurationError,
    ):
        raise TypeError("expected ServiceConfigurationError")

    return _api_error_response(
        status_code=500,
        code=(ApiErrorCode.SERVICE_CONFIGURATION_ERROR),
        detail=("RouteValue is temporarily unavailable. Please try again later."),
    )
