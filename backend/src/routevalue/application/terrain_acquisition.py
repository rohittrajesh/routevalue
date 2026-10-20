"""Acquire provider-neutral terrain profiles without affecting trip decisions."""

from collections.abc import Callable, Sequence
from dataclasses import replace

from routevalue.application.models import ProvidedRoute, RouteGeometry
from routevalue.application.terrain import (
    ElevationSample,
    GeometryFidelity,
    TerrainAcquisitionResult,
    TerrainProfile,
    TerrainUnavailableReason,
)
from routevalue.application.terrain_batching import MAX_ELEVATION_BATCH_SIZE, plan_elevation_batches
from routevalue.application.terrain_ports import (
    ElevationProvider,
    ElevationProviderError,
    ElevationProviderQuotaError,
    ElevationProviderRejectedError,
    ElevationProviderResponseError,
    ElevationProviderUnavailableError,
)
from routevalue.application.terrain_sampling import (
    MAX_TERRAIN_SAMPLES_PER_ROUTE,
    TerrainSampleLocation,
    sample_route_geometry,
)


def _unknown_samples(
    locations: Sequence[TerrainSampleLocation],
) -> tuple[ElevationSample, ...]:
    """Preserve requested coordinates and offsets without inventing elevations."""

    return tuple(
        ElevationSample(
            point=location.point,
            distance_meters=location.distance_meters,
            elevation_meters=None,
        )
        for location in locations
    )


def _validate_observations(
    observations: tuple[ElevationSample, ...],
    expected: tuple[TerrainSampleLocation, ...],
) -> None:
    """Reject omitted, reordered, or mismatched provider observations."""

    if len(observations) != len(expected):
        raise ElevationProviderResponseError("elevation batch length does not match request")

    if any(
        not isinstance(observation, ElevationSample)
        or observation.point != location.point
        or observation.distance_meters != location.distance_meters
        for observation, location in zip(observations, expected)
    ):
        raise ElevationProviderResponseError("elevation batch does not match requested locations")


class TerrainAcquisitionService:
    """Enrich independent candidate routes with optional, ordered terrain data.

    Supply a guarded per-trip ElevationProvider from the composition boundary.
    The service does not acquire routes, estimate energy, or make decisions.
    """

    def __init__(
        self,
        *,
        elevation_provider: ElevationProvider,
        enabled: bool = False,
        geometry_fidelity: GeometryFidelity = GeometryFidelity.UNKNOWN,
        elevation_provider_factory: Callable[[], ElevationProvider] | None = None,
        trip_request_budget: int | None = None,
    ) -> None:
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a boolean")
        if not isinstance(geometry_fidelity, GeometryFidelity):
            raise TypeError("geometry_fidelity must be a GeometryFidelity")
        self._elevation_provider = elevation_provider
        self._enabled = enabled
        self._geometry_fidelity = geometry_fidelity
        self._elevation_provider_factory = elevation_provider_factory
        if trip_request_budget is not None and (
            isinstance(trip_request_budget, bool)
            or not isinstance(trip_request_budget, int)
            or trip_request_budget < 1
        ):
            raise ValueError("trip request budget must be a positive integer")
        self._trip_request_budget = trip_request_budget

    def acquire_routes(
        self,
        routes: Sequence[ProvidedRoute],
    ) -> tuple[TerrainAcquisitionResult, ...]:
        """Return one terrain outcome per input route in stable original order.

        A failed batch is marked missing; successful earlier batches are retained.
        A quota failure stops additional calls for the remainder of this trip.
        Other provider failures are isolated to the current route.
        """

        provided_routes = tuple(routes)
        if not self._enabled:
            return tuple(
                TerrainAcquisitionResult(
                    route_index=index,
                    unavailable_reason=TerrainUnavailableReason.DISABLED,
                )
                for index in range(len(provided_routes))
            )

        results: list[TerrainAcquisitionResult] = []
        quota_exhausted = False
        unique_shapes = {
            (item.route.distance_meters, item.geometry)
            for item in provided_routes
            if item.geometry is not None and item.route.distance_meters > 0
        }
        max_samples = MAX_TERRAIN_SAMPLES_PER_ROUTE
        if self._trip_request_budget is not None and unique_shapes:
            # The existing sampler increases spacing under a hard sample cap.
            # Give every distinct geometry the same bounded request allowance;
            # never spend the entire trip budget on the first long candidate.
            batches_per_shape = max(1, self._trip_request_budget // len(unique_shapes))
            max_samples = min(max_samples, batches_per_shape * MAX_ELEVATION_BATCH_SIZE)
        acquired_shapes: dict[tuple[int, RouteGeometry | None], TerrainAcquisitionResult] = {}
        # A service may be reused by diagnostics or a future composition layer.
        # Reset only the trip allowance; the shared daily gate remains intact.
        provider = (
            self._elevation_provider_factory()
            if self._elevation_provider_factory is not None
            else self._elevation_provider
        )

        for index, provided in enumerate(provided_routes):
            shape = (provided.route.distance_meters, provided.geometry)
            if self._trip_request_budget is not None and shape in acquired_shapes:
                # Same geometry/distance, different traffic time or toll facts:
                # reuse only terrain and preserve every original candidate index.
                results.append(replace(acquired_shapes[shape], route_index=index))
                continue
            sampling = sample_route_geometry(
                provided.geometry,
                route_distance_meters=provided.route.distance_meters,
                max_samples=max_samples,
            )
            if sampling.unavailable_reason is not None:
                results.append(
                    TerrainAcquisitionResult(
                        route_index=index,
                        unavailable_reason=sampling.unavailable_reason,
                    )
                )
                continue

            if quota_exhausted:
                results.append(
                    TerrainAcquisitionResult(
                        route_index=index,
                        unavailable_reason=TerrainUnavailableReason.REQUEST_BUDGET_EXCEEDED,
                    )
                )
                continue

            plan = plan_elevation_batches(sampling.locations)
            collected: list[ElevationSample] = []
            failure: TerrainUnavailableReason | None = None

            for batch_index, batch in enumerate(plan.batches):
                try:
                    observations = tuple(provider.get_elevations(batch))
                    _validate_observations(observations, batch)
                except ElevationProviderQuotaError:
                    failure = TerrainUnavailableReason.REQUEST_BUDGET_EXCEEDED
                    quota_exhausted = True
                except ElevationProviderRejectedError:
                    failure = TerrainUnavailableReason.PROVIDER_REJECTED
                except ElevationProviderResponseError:
                    failure = TerrainUnavailableReason.INVALID_PROVIDER_RESPONSE
                except ElevationProviderUnavailableError:
                    failure = TerrainUnavailableReason.PROVIDER_UNAVAILABLE
                except ElevationProviderError:
                    failure = TerrainUnavailableReason.PROVIDER_UNAVAILABLE
                else:
                    collected.extend(observations)
                    continue

                for pending in plan.batches[batch_index:]:
                    collected.extend(_unknown_samples(pending))
                break

            if any(sample.elevation_meters is not None for sample in collected):
                results.append(
                    TerrainAcquisitionResult(
                        route_index=index,
                        profile=TerrainProfile(
                            route_distance_meters=provided.route.distance_meters,
                            samples=tuple(collected),
                            geometry_fidelity=self._geometry_fidelity,
                        ),
                    )
                )
            else:
                results.append(
                    TerrainAcquisitionResult(
                        route_index=index,
                        unavailable_reason=failure or TerrainUnavailableReason.NO_ELEVATION_DATA,
                    )
                )
            if self._trip_request_budget is not None:
                acquired_shapes[shape] = results[-1]

        return tuple(results)
