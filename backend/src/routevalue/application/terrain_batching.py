"""Pure bounded batching of terrain coordinates before any elevation API call."""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from math import isfinite

from routevalue.application.terrain_sampling import TerrainSampleLocation

MAX_ELEVATION_BATCH_SIZE = 100
MAX_ROUTE_SAMPLE_COUNT = 256


@dataclass(frozen=True, slots=True)
class ElevationBatchPlan:
    """Ordered batches that preserve every requested route-distance location."""

    batches: tuple[tuple[TerrainSampleLocation, ...], ...]

    @property
    def request_count(self) -> int:
        return len(self.batches)

    @property
    def sample_count(self) -> int:
        return sum(len(batch) for batch in self.batches)


def plan_elevation_batches(
    locations: Sequence[TerrainSampleLocation],
    *,
    max_batch_size: int = MAX_ELEVATION_BATCH_SIZE,
    max_samples: int = MAX_ROUTE_SAMPLE_COUNT,
) -> ElevationBatchPlan:
    """Partition at most 256 ordered locations into provider-safe batches.

    No network requests are made. A per-trip budget across multiple routes
    is enforced separately by the guarded elevation provider.
    """

    if isinstance(max_batch_size, bool) or not isinstance(max_batch_size, int):
        raise TypeError("max_batch_size must be an integer")

    if not 1 <= max_batch_size <= MAX_ELEVATION_BATCH_SIZE:
        raise ValueError("max_batch_size must be between 1 and 100")

    if isinstance(max_samples, bool) or not isinstance(max_samples, int):
        raise TypeError("max_samples must be an integer")

    if not 1 <= max_samples <= MAX_ROUTE_SAMPLE_COUNT:
        raise ValueError("max_samples must be between 1 and 256")

    ordered = tuple(locations)

    if len(ordered) > max_samples:
        raise ValueError("elevation plan exceeds maximum route sample count")

    if any(not isinstance(item, TerrainSampleLocation) for item in ordered):
        raise TypeError("locations must contain TerrainSampleLocation values")

    if any(
        not isfinite(item.point.latitude) or not isfinite(item.point.longitude) for item in ordered
    ):
        raise ValueError("sample coordinates must be finite")

    if any(
        later.distance_meters <= earlier.distance_meters for earlier, later in pairwise(ordered)
    ):
        raise ValueError("sample distances must strictly increase")

    return ElevationBatchPlan(
        batches=tuple(
            ordered[start : start + max_batch_size]
            for start in range(0, len(ordered), max_batch_size)
        )
    )
