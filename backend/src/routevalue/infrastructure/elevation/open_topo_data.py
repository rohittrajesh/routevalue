"""Open Topo Data public elevation API adapter; no implicit live calls."""

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from math import isfinite

import httpx

from routevalue.application.terrain import ElevationSample
from routevalue.application.terrain_ports import (
    ElevationProviderQuotaError,
    ElevationProviderRejectedError,
    ElevationProviderResponseError,
    ElevationProviderUnavailableError,
)
from routevalue.application.terrain_sampling import TerrainSampleLocation

OPEN_TOPO_DATA_BASE_URL = "https://api.opentopodata.org/v1"
OPEN_TOPO_DATA_MAX_LOCATIONS = 100
OPEN_TOPO_DATA_DEFAULT_DATASET = "ned10m"

_ALLOWED_DATASETS = frozenset({"ned10m", "mapzen"})
_COORDINATE_TOLERANCE_DEGREES = 0.000001


class OpenTopoDataElevationProvider:
    """Retrieve one bounded batch from a fixed public HTTPS API endpoint.

    Rate and daily budgets across batches/trips belong to M6-E/F.
    This adapter does not retry, cache, or automatically issue requests.
    """

    def __init__(
        self,
        *,
        client: httpx.Client,
        dataset: str = OPEN_TOPO_DATA_DEFAULT_DATASET,
    ) -> None:
        if dataset not in _ALLOWED_DATASETS:
            raise ValueError("unsupported Open Topo Data dataset")

        self._client = client
        self._dataset = dataset

    def get_elevations(
        self,
        locations: Sequence[TerrainSampleLocation],
    ) -> tuple[ElevationSample, ...]:
        """Fetch at most 100 ordered locations with one POST, or return empty."""

        batch = tuple(locations)

        if not batch:
            return ()

        if len(batch) > OPEN_TOPO_DATA_MAX_LOCATIONS:
            raise ValueError("elevation batch exceeds 100 locations")

        if any(not isinstance(item, TerrainSampleLocation) for item in batch):
            raise TypeError("locations must be TerrainSampleLocation instances")

        if any(
            not isfinite(item.point.latitude) or not isfinite(item.point.longitude)
            for item in batch
        ):
            raise ValueError("elevation batch coordinates must be finite")

        if any(
            second.distance_meters <= first.distance_meters for first, second in pairwise(batch)
        ):
            raise ValueError("elevation batch distances must strictly increase")

        coordinates = "|".join(
            f"{item.point.latitude:.7f},{item.point.longitude:.7f}" for item in batch
        )

        try:
            response = self._client.post(
                f"{OPEN_TOPO_DATA_BASE_URL}/{self._dataset}",
                json={
                    "locations": coordinates,
                    "interpolation": "bilinear",
                    "nodata_value": "null",
                },
            )
        except httpx.RequestError as exc:
            raise ElevationProviderUnavailableError("elevation provider request failed") from exc

        if response.status_code == 429:
            raise ElevationProviderQuotaError("elevation provider rate limit exceeded")

        if 500 <= response.status_code <= 599:
            raise ElevationProviderUnavailableError("elevation provider is unavailable")

        if not response.is_success:
            raise ElevationProviderRejectedError("elevation provider rejected request")

        try:
            payload: object = response.json()
        except ValueError as exc:
            raise ElevationProviderResponseError(
                "elevation provider returned invalid JSON"
            ) from exc

        return _normalize_response(
            payload,
            batch,
            dataset=self._dataset,
        )


def _is_matching_coordinate(
    actual: object,
    expected: float,
    *,
    longitude: bool,
) -> bool:
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return False

    try:
        number = float(actual)
    except (OverflowError, ValueError):
        return False

    if not isfinite(number):
        return False

    difference = abs(number - expected)

    if longitude:
        difference = min(
            difference,
            abs(difference - 360),
        )

    return difference <= _COORDINATE_TOLERANCE_DEGREES


def _parse_elevation(
    raw: object,
) -> Decimal | None:
    if raw is None:
        return None

    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ElevationProviderResponseError("elevation must be a finite JSON number or null")

    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ElevationProviderResponseError("invalid elevation value") from exc

    if not value.is_finite():
        raise ElevationProviderResponseError("elevation must be finite")

    return value


def _normalize_response(
    payload: object,
    locations: tuple[TerrainSampleLocation, ...],
    *,
    dataset: str,
) -> tuple[ElevationSample, ...]:
    if not isinstance(payload, dict):
        raise ElevationProviderResponseError("elevation response must be an object")

    status = payload.get("status")

    if status == "SERVER_ERROR":
        raise ElevationProviderUnavailableError("elevation provider reported a server error")

    if status == "INVALID_REQUEST":
        raise ElevationProviderRejectedError("elevation provider rejected request")

    if status != "OK":
        raise ElevationProviderResponseError("unrecognized elevation response status")

    results = payload.get("results")

    if not isinstance(results, list) or len(results) != len(locations):
        raise ElevationProviderResponseError("elevation result count does not match request")

    normalized: list[ElevationSample] = []

    for result, requested in zip(
        results,
        locations,
        strict=True,
    ):
        if not isinstance(result, dict) or "elevation" not in result:
            raise ElevationProviderResponseError("elevation result has invalid structure")

        location = result.get("location")

        if not isinstance(location, dict) or not (
            _is_matching_coordinate(
                location.get("lat"),
                requested.point.latitude,
                longitude=False,
            )
            and _is_matching_coordinate(
                location.get("lng"),
                requested.point.longitude,
                longitude=True,
            )
        ):
            raise ElevationProviderResponseError("elevation coordinates do not match request")

        elevation = _parse_elevation(result["elevation"])

        if elevation is not None and result.get("dataset") != dataset:
            raise ElevationProviderResponseError("elevation source dataset does not match request")

        normalized.append(
            ElevationSample(
                point=requested.point,
                distance_meters=requested.distance_meters,
                elevation_meters=elevation,
                resolution_meters=None,
            )
        )

    return tuple(normalized)
