"""Offline Census-based geographic resolution for gasoline pricing."""

from io import BytesIO
from math import cos, radians, sin
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import shapefile  # type: ignore[import-untyped]
from shapely import transform  # type: ignore[import-untyped]
from shapely.geometry import Point, shape  # type: ignore[import-untyped]
from shapely.geometry.base import BaseGeometry  # type: ignore[import-untyped]

from routevalue.application.gasoline_price_geography import (
    PricingJurisdiction,
    PricingJurisdictionResult,
)
from routevalue.application.models import ResolvedLocation

DEFAULT_BOUNDARY_ARCHIVE = Path(__file__).resolve().parent / "data" / "cb_2025_us_state_500k.zip"

EARTH_RADIUS_METERS = 6_371_008.8

# Candidate uncertainty distance, not a guarantee of boundary accuracy.
BOUNDARY_TOLERANCE_METERS = 250.0

EXCLUDED_TERRITORIES = frozenset({"PR", "GU", "VI", "AS", "MP"})


def _distance_to_boundary_meters(
    *,
    geometry: BaseGeometry,
    longitude: float,
    latitude: float,
) -> float:
    """Approximate local boundary distance in meters.

    A spherical azimuthal equidistant projection is centered
    on the query coordinate.

    This method does not require pyproj or external requests.
    """

    longitude_origin = radians(longitude)
    latitude_origin = radians(latitude)

    sin_origin = sin(latitude_origin)
    cos_origin = cos(latitude_origin)

    def project(coordinates: np.ndarray) -> np.ndarray:
        longitudes = np.radians(coordinates[:, 0])
        latitudes = np.radians(coordinates[:, 1])

        delta_longitudes = longitudes - longitude_origin

        cos_latitudes = np.cos(latitudes)
        sin_latitudes = np.sin(latitudes)

        cosine_angle = sin_origin * sin_latitudes + cos_origin * cos_latitudes * np.cos(
            delta_longitudes
        )

        central_angles = np.arccos(np.clip(cosine_angle, -1.0, 1.0))

        sine_angles = np.sin(central_angles)

        if np.any((central_angles > 3.14159 - 1e-6) & (np.abs(sine_angles) < 1e-6)):
            raise ValueError("boundary projection is numerically ambiguous")

        scales = np.divide(
            central_angles,
            sine_angles,
            out=np.ones_like(central_angles),
            where=np.abs(sine_angles) > 1e-12,
        )

        x = EARTH_RADIUS_METERS * scales * cos_latitudes * np.sin(delta_longitudes)

        y = (
            EARTH_RADIUS_METERS
            * scales
            * (cos_origin * sin_latitudes - sin_origin * cos_latitudes * np.cos(delta_longitudes))
        )

        return np.column_stack((x, y))

    projected_boundary = transform(
        geometry.boundary,
        project,
    )

    distance = Point(0.0, 0.0).distance(projected_boundary)

    if not np.isfinite(distance):
        raise ValueError("boundary distance is not finite")

    return float(distance)


class CensusPricingJurisdictionResolver:
    """Classify coordinates using packaged Census polygons.

    State geometries are loaded at construction time.
    A process-scoped lifecycle provider can reuse this instance.

    Unmatched, overlapping, or boundary-ambiguous positions
    are classified as UNKNOWN.
    """

    def __init__(
        self,
        archive_path: Path = DEFAULT_BOUNDARY_ARCHIVE,
    ) -> None:
        self._states = self._load_states(archive_path)

    @staticmethod
    def _load_states(
        archive_path: Path,
    ) -> tuple[tuple[str, BaseGeometry], ...]:
        """Read eligible state geometries from the Census archive."""

        with ZipFile(archive_path) as archive:
            names = archive.namelist()

            def read_file(extension: str) -> BytesIO:
                matching = [name for name in names if name.endswith(extension)]

                if len(matching) != 1:
                    raise ValueError(f"expected exactly one {extension} file")

                return BytesIO(archive.read(matching[0]))

            reader = shapefile.Reader(
                shp=read_file(".shp"),
                shx=read_file(".shx"),
                dbf=read_file(".dbf"),
            )

            states: list[tuple[str, BaseGeometry]] = []

            for record in reader.iterShapeRecords():
                attributes = record.record.as_dict()
                state_code = attributes.get("STUSPS")

                if not isinstance(state_code, str):
                    raise TypeError("Census record has invalid state code")

                if state_code in EXCLUDED_TERRITORIES:
                    continue

                geometry = shape(record.shape.__geo_interface__)

                if geometry.is_empty or not geometry.is_valid:
                    raise ValueError("Census record has invalid geometry")

                states.append((state_code, geometry))

        if not states:
            raise ValueError("no valid Census state geometries")

        return tuple(states)

    def resolve(
        self,
        location: ResolvedLocation,
    ) -> PricingJurisdictionResult:
        """Classify one resolved geographic location.

        Exact polygon boundaries are ambiguous regardless of
        numerical precision in metric projection.
        """

        if not isinstance(location, ResolvedLocation):
            raise TypeError("location must be a ResolvedLocation")

        point = Point(
            location.longitude,
            location.latitude,
        )

        matches = [
            (state_code, geometry)
            for state_code, geometry in self._states
            if geometry.covers(point)
        ]

        if len(matches) != 1:
            return PricingJurisdictionResult(jurisdiction=PricingJurisdiction.UNKNOWN)

        state_code, geometry = matches[0]

        # Exact boundary containment takes precedence over the
        # approximate metric-distance calculation.
        if geometry.boundary.covers(point):
            return PricingJurisdictionResult(jurisdiction=PricingJurisdiction.UNKNOWN)

        try:
            distance_meters = _distance_to_boundary_meters(
                geometry=geometry,
                longitude=location.longitude,
                latitude=location.latitude,
            )
        except (ValueError, OverflowError, FloatingPointError):
            return PricingJurisdictionResult(jurisdiction=PricingJurisdiction.UNKNOWN)

        if distance_meters <= BOUNDARY_TOLERANCE_METERS:
            jurisdiction = PricingJurisdiction.UNKNOWN

        elif state_code == "CA":
            jurisdiction = PricingJurisdiction.CALIFORNIA

        else:
            jurisdiction = PricingJurisdiction.OTHER_US

        return PricingJurisdictionResult(jurisdiction=jurisdiction)
