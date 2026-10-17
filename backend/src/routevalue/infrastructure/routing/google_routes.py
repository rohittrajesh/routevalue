"""Google Routes response normalization for the RouteValue infrastructure layer."""

from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from time import sleep
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteGeometry,
    RoutePoint,
    RouteSearchRequest,
)
from routevalue.domain.models import RouteCandidate

_NANOS_PER_UNIT = Decimal(1000000000)

GOOGLE_ROUTES_FIELD_MASK = (
    "routes.distanceMeters,routes.duration,routes.travelAdvisory.tollInfo,routes.polyline"
)

GOOGLE_ROUTES_COMPUTE_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

_GOOGLE_ROUTES_MAX_ATTEMPTS = 3

_GOOGLE_ROUTES_RETRY_DELAYS_SECONDS = (
    0.25,
    0.5,
)

type GooglePolylineQuality = Literal["OVERVIEW", "HIGH_QUALITY"]


def _validate_polyline_quality(quality: str) -> None:
    if quality not in ("OVERVIEW", "HIGH_QUALITY"):
        raise ValueError("polyline_quality must be OVERVIEW or HIGH_QUALITY")


class GoogleRoutesError(RuntimeError):
    """Base error for the Google Routes infrastructure adapter."""


class GoogleRoutesTransportError(GoogleRoutesError):
    """Raised when the request cannot successfully reach Google Routes."""


class GoogleRoutesHTTPError(GoogleRoutesError):
    """Raised when Google Routes returns a non-success HTTP response."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"Google Routes returned HTTP {status_code}")


class GoogleRoutesResponseError(GoogleRoutesError):
    """Raised when a Google response cannot be safely normalized."""


class GoogleRoutesRouteProvider:
    """Retrieve and normalize route candidates from Google Routes."""

    def __init__(
        self,
        *,
        api_key: str,
        client: httpx.Client,
        sleeper: Callable[[float], None] = sleep,
        polyline_quality: GooglePolylineQuality = "OVERVIEW",
    ) -> None:
        _validate_polyline_quality(polyline_quality)
        self._api_key = api_key
        self._client = client
        self._sleeper = sleeper
        self._polyline_quality = polyline_quality

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> tuple[ProvidedRoute, ...]:
        """Return a stable merged set of normalized Google routes."""

        baseline_routes = self._request_routes(
            request,
            avoid_tolls=False,
        )

        avoid_tolls_routes = self._request_routes(
            request,
            avoid_tolls=True,
        )

        return _merge_unique_routes(
            baseline_routes,
            avoid_tolls_routes,
        )

    def _request_routes(
        self,
        request: RouteSearchRequest,
        *,
        avoid_tolls: bool,
    ) -> tuple[ProvidedRoute, ...]:
        """Execute one Google Routes acquisition with bounded retries."""

        for attempt_index in range(_GOOGLE_ROUTES_MAX_ATTEMPTS):
            try:
                response = self._client.post(
                    GOOGLE_ROUTES_COMPUTE_URL,
                    headers={
                        "X-Goog-Api-Key": self._api_key,
                        "X-Goog-FieldMask": GOOGLE_ROUTES_FIELD_MASK,
                    },
                    json=build_google_routes_request_payload(
                        request,
                        avoid_tolls=avoid_tolls,
                        polyline_quality=self._polyline_quality,
                    ),
                )
            except httpx.RequestError as exc:
                if attempt_index == _GOOGLE_ROUTES_MAX_ATTEMPTS - 1:
                    raise GoogleRoutesTransportError("Google Routes request failed") from exc

                self._sleeper(_GOOGLE_ROUTES_RETRY_DELAYS_SECONDS[attempt_index])
                continue

            if not response.is_success:
                if (
                    _is_retryable_http_status(response.status_code)
                    and attempt_index < _GOOGLE_ROUTES_MAX_ATTEMPTS - 1
                ):
                    self._sleeper(_GOOGLE_ROUTES_RETRY_DELAYS_SECONDS[attempt_index])
                    continue

                raise GoogleRoutesHTTPError(response.status_code)

            try:
                payload: object = response.json()
            except ValueError as exc:
                raise GoogleRoutesResponseError("Google Routes response is not valid JSON") from exc

            return parse_google_provided_routes_response(payload)

        raise AssertionError("Google Routes retry loop exhausted unexpectedly")


class _GoogleMoney(BaseModel):
    """Provider-specific representation of a Google monetary amount."""

    model_config = ConfigDict(extra="ignore")

    currency_code: str = Field(alias="currencyCode")
    units: str = "0"
    nanos: int = Field(
        default=0,
        ge=-999_999_999,
        le=999_999_999,
    )


class _GoogleTollInfo(BaseModel):
    """Provider-specific toll information returned by Google."""

    model_config = ConfigDict(extra="ignore")

    estimated_price: tuple[_GoogleMoney, ...] = Field(
        default=(),
        alias="estimatedPrice",
    )


class _GoogleTravelAdvisory(BaseModel):
    """Provider-specific route travel advisory."""

    model_config = ConfigDict(extra="ignore")

    toll_info: _GoogleTollInfo | None = Field(
        default=None,
        alias="tollInfo",
    )


class _GooglePolyline(BaseModel):
    """Provider-specific Google route polyline."""

    model_config = ConfigDict(extra="ignore")

    geo_json_linestring: object | None = Field(
        default=None,
        alias="geoJsonLinestring",
    )


class _GoogleRoute(BaseModel):
    """Provider-specific route fields required by RouteValue."""

    model_config = ConfigDict(extra="ignore")

    distance_meters: int = Field(
        alias="distanceMeters",
        ge=0,
    )
    duration: str

    travel_advisory: _GoogleTravelAdvisory | None = Field(
        default=None,
        alias="travelAdvisory",
    )

    polyline: _GooglePolyline | None = None


class _GoogleComputeRoutesResponse(BaseModel):
    """Subset of a Google Compute Routes response required by RouteValue."""

    model_config = ConfigDict(extra="ignore")

    routes: tuple[_GoogleRoute, ...] = ()


def _to_google_waypoint(
    location: ResolvedLocation,
) -> dict[str, object]:
    """Convert a provider-neutral location into a Google Routes waypoint."""

    if location.source == "google_places" and location.source_id is not None:
        return {
            "placeId": location.source_id,
        }

    return {
        "location": {
            "latLng": {
                "latitude": location.latitude,
                "longitude": location.longitude,
            }
        }
    }


def build_google_routes_request_payload(
    request: RouteSearchRequest,
    *,
    avoid_tolls: bool = False,
    polyline_quality: GooglePolylineQuality = "OVERVIEW",
) -> dict[str, object]:
    """Build a Google Compute Routes request from provider-neutral inputs."""

    _validate_polyline_quality(polyline_quality)

    payload: dict[str, object] = {
        "origin": _to_google_waypoint(request.origin),
        "destination": _to_google_waypoint(request.destination),
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "computeAlternativeRoutes": True,
        "polylineEncoding": "GEO_JSON_LINESTRING",
        "polylineQuality": polyline_quality,
        "extraComputations": ["TOLLS"],
    }

    if avoid_tolls:
        payload["routeModifiers"] = {
            "avoidTolls": True,
        }

    return payload


def _parse_duration_seconds(duration: str) -> int:
    """Convert Google's protobuf duration string to whole RouteValue seconds."""

    if not duration.endswith("s"):
        raise GoogleRoutesResponseError("Google route duration must end with 's'")

    try:
        seconds = Decimal(duration[:-1])
    except InvalidOperation as exc:
        raise GoogleRoutesResponseError("Google route duration is invalid") from exc

    if not seconds.is_finite() or seconds < 0:
        raise GoogleRoutesResponseError("Google route duration must be a finite nonnegative value")

    return int(
        seconds.to_integral_value(
            rounding=ROUND_HALF_UP,
        )
    )


def _parse_google_money(money: _GoogleMoney) -> Decimal:
    """Convert Google's units-and-nanos money representation exactly."""

    try:
        units = Decimal(money.units)
    except InvalidOperation as exc:
        raise GoogleRoutesResponseError("Google money units are invalid") from exc

    amount = units + (Decimal(money.nanos) / _NANOS_PER_UNIT)

    if not amount.is_finite() or amount < 0:
        raise GoogleRoutesResponseError("Google toll amount must be a finite nonnegative value")

    return amount


def _parse_toll_cost(route: _GoogleRoute) -> Decimal | None:
    """Normalize Google's toll semantics into RouteValue money semantics."""

    if route.travel_advisory is None or route.travel_advisory.toll_info is None:
        return Decimal(0)

    prices = route.travel_advisory.toll_info.estimated_price

    if len(prices) != 1:
        return None

    price = prices[0]

    if price.currency_code != "USD":
        return None

    return _parse_google_money(price)


def _parse_route_geometry(
    polyline: _GooglePolyline | None,
) -> RouteGeometry | None:
    """Normalize a Google GeoJSON LineString into RouteValue geometry."""

    if polyline is None or polyline.geo_json_linestring is None:
        return None

    geo_json = polyline.geo_json_linestring

    if not isinstance(geo_json, dict):
        return None

    if geo_json.get("type") != "LineString":
        return None

    coordinates = geo_json.get("coordinates")

    if not isinstance(coordinates, list):
        return None

    points: list[RoutePoint] = []

    for coordinate in coordinates:
        if not isinstance(coordinate, list) or len(coordinate) < 2:
            return None

        longitude = coordinate[0]
        latitude = coordinate[1]

        if (
            isinstance(longitude, bool)
            or not isinstance(longitude, (int, float))
            or isinstance(latitude, bool)
            or not isinstance(latitude, (int, float))
        ):
            return None

        try:
            point = RoutePoint(
                latitude=float(latitude),
                longitude=float(longitude),
            )
        except ValueError:
            return None

        points.append(point)

    try:
        return RouteGeometry(points=tuple(points))
    except ValueError:
        return None


def _validate_google_routes_response(
    payload: object,
) -> _GoogleComputeRoutesResponse:
    """Validate the provider response fields RouteValue depends on."""

    try:
        return _GoogleComputeRoutesResponse.model_validate(payload)
    except ValidationError as exc:
        raise GoogleRoutesResponseError("Google Routes response has an invalid structure") from exc


def _to_route_candidate(route: _GoogleRoute) -> RouteCandidate:
    """Normalize one Google route into the RouteValue decision model."""

    return RouteCandidate(
        distance_meters=route.distance_meters,
        duration_seconds=_parse_duration_seconds(route.duration),
        toll_cost=_parse_toll_cost(route),
    )


def parse_google_routes_response(
    payload: object,
) -> tuple[RouteCandidate, ...]:
    """Normalize Google route candidates in provider-returned order."""

    response = _validate_google_routes_response(payload)

    return tuple(_to_route_candidate(route) for route in response.routes)


def parse_google_provided_routes_response(
    payload: object,
) -> tuple[ProvidedRoute, ...]:
    """Normalize Google routes and optional geometry in provider order."""

    response = _validate_google_routes_response(payload)

    return tuple(
        ProvidedRoute(
            route=_to_route_candidate(route),
            geometry=_parse_route_geometry(route.polyline),
        )
        for route in response.routes
    )


def _merge_unique_routes(
    *route_groups: tuple[ProvidedRoute, ...],
) -> tuple[ProvidedRoute, ...]:
    """Merge route groups while preserving the first exact candidate."""

    unique_routes: list[ProvidedRoute] = []

    for route_group in route_groups:
        for provided_route in route_group:
            duplicate = any(existing.route == provided_route.route for existing in unique_routes)

            if not duplicate:
                unique_routes.append(provided_route)

    return tuple(unique_routes)


def _is_retryable_http_status(status_code: int) -> bool:
    """Return whether a Google HTTP status represents a transient failure."""

    return status_code == 429 or 500 <= status_code <= 599
