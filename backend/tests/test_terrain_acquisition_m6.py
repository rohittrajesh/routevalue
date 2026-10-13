"""M6-F: provider-neutral terrain orchestration, with no live HTTP calls."""

from collections.abc import Sequence
from decimal import Decimal

import pytest

from routevalue.application.models import ProvidedRoute, RouteGeometry, RoutePoint
from routevalue.application.terrain import (
    ElevationSample,
    GeometryFidelity,
    TerrainAcquisitionStatus,
    TerrainUnavailableReason,
)
from routevalue.application.terrain_acquisition import TerrainAcquisitionService
from routevalue.application.terrain_ports import (
    ElevationProviderError,
    ElevationProviderQuotaError,
    ElevationProviderRejectedError,
    ElevationProviderResponseError,
    ElevationProviderUnavailableError,
)
from routevalue.application.terrain_sampling import TerrainSampleLocation
from routevalue.domain.models import RouteCandidate
from routevalue.infrastructure.elevation.safety import PublicElevationCallGate


class FakeElevationProvider:
    def __init__(
        self,
        *,
        failures: dict[int, Exception] | None = None,
        missing_at: set[int] | None = None,
        malformed_at: set[int] | None = None,
    ) -> None:
        self.calls: list[tuple[TerrainSampleLocation, ...]] = []
        self.failures = failures or {}
        self.missing_at = missing_at or set()
        self.malformed_at = malformed_at or set()

    def get_elevations(
        self, locations: Sequence[TerrainSampleLocation]
    ) -> tuple[ElevationSample, ...]:
        batch = tuple(locations)
        index = len(self.calls)
        self.calls.append(batch)

        if index in self.failures:
            raise self.failures[index]

        observations = tuple(
            ElevationSample(
                point=location.point,
                distance_meters=location.distance_meters,
                elevation_meters=(
                    None if index in self.missing_at else Decimal(location.distance_meters) / 100
                ),
            )
            for location in batch
        )

        if index in self.malformed_at:
            return observations[:-1]

        return observations


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _route(
    distance_meters: int = 1_000,
    *,
    geometry: RouteGeometry | None = None,
) -> ProvidedRoute:
    if geometry is None:
        geometry = RouteGeometry(
            points=(
                RoutePoint(latitude=32.88, longitude=-117.23),
                RoutePoint(latitude=32.90, longitude=-117.21),
            )
        )

    return ProvidedRoute(
        route=RouteCandidate(
            distance_meters=distance_meters,
            duration_seconds=900,
            toll_cost=Decimal(0),
        ),
        geometry=geometry,
    )


def _service(
    provider: FakeElevationProvider,
    *,
    enabled: bool = True,
) -> TerrainAcquisitionService:
    return TerrainAcquisitionService(
        elevation_provider=provider,
        enabled=enabled,
    )


def test_empty_trip_has_no_calls_or_results() -> None:
    provider = FakeElevationProvider()
    assert _service(provider).acquire_routes(()) == ()
    assert provider.calls == []


def test_disabled_service_preserves_route_count_without_network() -> None:
    provider = FakeElevationProvider()
    routes = (_route(), _route(2_000))
    results = _service(provider, enabled=False).acquire_routes(routes)

    assert tuple(item.route_index for item in results) == (0, 1)
    assert all(item.status is TerrainAcquisitionStatus.UNAVAILABLE for item in results)
    assert all(item.unavailable_reason is TerrainUnavailableReason.DISABLED for item in results)
    assert provider.calls == []


def test_one_route_builds_distance_aligned_profile_and_grades() -> None:
    provider = FakeElevationProvider()
    result = _service(provider).acquire_routes((_route(),))[0]

    assert result.status is TerrainAcquisitionStatus.COMPLETE
    assert result.profile is not None
    assert result.profile.route_distance_meters == 1_000

    assert tuple(s.distance_meters for s in result.profile.samples) == (
        0,
        250,
        500,
        750,
        1_000,
    )

    assert tuple(s.elevation_meters for s in result.profile.samples) == (
        Decimal(0),
        Decimal("2.5"),
        Decimal(5),
        Decimal("7.5"),
        Decimal(10),
    )

    assert tuple(grade.grade for grade in result.profile.grade_segments) == (Decimal("0.01"),) * 4

    assert len(provider.calls) == 1


def test_geometry_fidelity_is_configurable_and_provider_neutral() -> None:
    service = TerrainAcquisitionService(
        elevation_provider=FakeElevationProvider(),
        enabled=True,
        geometry_fidelity=GeometryFidelity.SIMPLIFIED,
    )

    result = service.acquire_routes((_route(),))[0]

    assert result.profile is not None
    assert result.profile.geometry_fidelity is GeometryFidelity.SIMPLIFIED


def test_duplicate_value_routes_remain_two_distinct_terrain_results() -> None:
    original = _route()

    alternate_geometry = RouteGeometry(
        points=(
            RoutePoint(32.88, -117.23),
            RoutePoint(32.92, -117.21),
        )
    )

    second = ProvidedRoute(
        route=original.route,
        geometry=alternate_geometry,
    )

    provider = FakeElevationProvider()
    results = _service(provider).acquire_routes((original, second))

    assert tuple(item.route_index for item in results) == (0, 1)
    assert len(provider.calls) == 2

    assert results[0].profile is not None
    assert results[1].profile is not None
    assert results[0].profile.samples[-1].point != results[1].profile.samples[-1].point


def test_missing_geometry_does_not_block_other_routes() -> None:
    provider = FakeElevationProvider()

    missing = ProvidedRoute(
        route=_route().route,
        geometry=None,
    )

    outcomes = _service(provider).acquire_routes((missing, _route()))

    assert outcomes[0].unavailable_reason is TerrainUnavailableReason.MISSING_GEOMETRY
    assert outcomes[1].status is TerrainAcquisitionStatus.COMPLETE
    assert len(provider.calls) == 1


def test_invalid_route_distance_is_explicitly_unavailable() -> None:
    outcome = _service(FakeElevationProvider()).acquire_routes((_route(0),))[0]

    assert outcome.unavailable_reason is TerrainUnavailableReason.INVALID_ROUTE_DISTANCE


def test_invalid_geometry_is_explicitly_unavailable() -> None:
    point = RoutePoint(32.88, -117.23)

    result = _service(FakeElevationProvider()).acquire_routes(
        (_route(1_000, geometry=RouteGeometry(points=(point, point))),)
    )[0]

    assert result.unavailable_reason is TerrainUnavailableReason.INVALID_GEOMETRY


def test_all_null_observations_do_not_create_a_fabricated_profile() -> None:
    provider = FakeElevationProvider(missing_at={0})
    result = _service(provider).acquire_routes((_route(),))[0]

    assert result.profile is None
    assert result.unavailable_reason is TerrainUnavailableReason.NO_ELEVATION_DATA


def test_partial_null_observations_preserve_the_unknown_grades() -> None:
    class OneMissingProvider(FakeElevationProvider):
        def get_elevations(
            self,
            locations: Sequence[TerrainSampleLocation],
        ) -> tuple[ElevationSample, ...]:
            known = super().get_elevations(locations)

            return tuple(
                ElevationSample(
                    point=sample.point,
                    distance_meters=sample.distance_meters,
                    elevation_meters=None if i == 2 else sample.elevation_meters,
                )
                for i, sample in enumerate(known)
            )

    result = _service(OneMissingProvider()).acquire_routes((_route(),))[0]

    assert result.status is TerrainAcquisitionStatus.PARTIAL
    assert result.profile is not None
    assert result.profile.missing_sample_count == 1

    assert tuple(segment.grade for segment in result.profile.grade_segments) == (
        Decimal("0.01"),
        None,
        None,
        Decimal("0.01"),
    )


def test_256_samples_are_batched_100_100_56() -> None:
    provider = FakeElevationProvider()
    result = _service(provider).acquire_routes((_route(100_000),))[0]

    assert result.status is TerrainAcquisitionStatus.COMPLETE
    assert [len(batch) for batch in provider.calls] == [100, 100, 56]

    assert result.profile is not None
    assert len(result.profile.samples) == 256
    assert result.profile.samples[0].distance_meters == 0
    assert result.profile.samples[-1].distance_meters == 100_000


def test_failed_second_batch_is_partial_and_does_not_query_remaining_batch() -> None:
    provider = FakeElevationProvider(failures={1: ElevationProviderUnavailableError("timeout")})

    result = _service(provider).acquire_routes((_route(100_000),))[0]

    assert result.status is TerrainAcquisitionStatus.PARTIAL
    assert result.profile is not None
    assert len(result.profile.samples) == 256
    assert result.profile.missing_sample_count == 156
    assert all(s.elevation_meters is None for s in result.profile.samples[100:])
    assert len(provider.calls) == 2


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (
            ElevationProviderUnavailableError("offline"),
            TerrainUnavailableReason.PROVIDER_UNAVAILABLE,
        ),
        (
            ElevationProviderRejectedError("bad"),
            TerrainUnavailableReason.PROVIDER_REJECTED,
        ),
        (
            ElevationProviderResponseError("bad json"),
            TerrainUnavailableReason.INVALID_PROVIDER_RESPONSE,
        ),
        (
            ElevationProviderError("unexpected adapter error"),
            TerrainUnavailableReason.PROVIDER_UNAVAILABLE,
        ),
    ],
)
def test_first_batch_failure_is_explicitly_unavailable(
    failure: Exception,
    expected: TerrainUnavailableReason,
) -> None:
    result = _service(FakeElevationProvider(failures={0: failure})).acquire_routes((_route(),))[0]

    assert result.unavailable_reason is expected
    assert result.profile is None


def test_nonquota_provider_failure_does_not_discard_other_route() -> None:
    provider = FakeElevationProvider(failures={0: ElevationProviderUnavailableError("temporary")})

    results = _service(provider).acquire_routes((_route(), _route(2_000)))

    assert results[0].unavailable_reason is TerrainUnavailableReason.PROVIDER_UNAVAILABLE
    assert results[1].status is TerrainAcquisitionStatus.COMPLETE
    assert len(provider.calls) == 2


def test_quota_failure_stops_all_later_requests_this_trip() -> None:
    provider = FakeElevationProvider(failures={0: ElevationProviderQuotaError("429")})

    results = _service(provider).acquire_routes((_route(), _route(), _route()))

    assert [result.unavailable_reason for result in results] == [
        TerrainUnavailableReason.REQUEST_BUDGET_EXCEEDED
    ] * 3

    assert len(provider.calls) == 1


def test_quota_in_second_batch_preserves_first_batch_as_partial() -> None:
    provider = FakeElevationProvider(failures={1: ElevationProviderQuotaError("daily")})

    results = _service(provider).acquire_routes((_route(100_000), _route()))

    assert results[0].status is TerrainAcquisitionStatus.PARTIAL
    assert results[0].profile is not None
    assert results[0].profile.missing_sample_count == 156
    assert results[1].unavailable_reason is TerrainUnavailableReason.REQUEST_BUDGET_EXCEEDED
    assert len(provider.calls) == 2


def test_wrong_length_response_does_not_claim_known_elevations() -> None:
    provider = FakeElevationProvider(malformed_at={0})
    result = _service(provider).acquire_routes((_route(),))[0]

    assert result.unavailable_reason is TerrainUnavailableReason.INVALID_PROVIDER_RESPONSE


def test_wrong_route_distance_in_result_is_rejected() -> None:
    class ShiftedProvider(FakeElevationProvider):
        def get_elevations(
            self,
            locations: Sequence[TerrainSampleLocation],
        ) -> tuple[ElevationSample, ...]:
            initial = super().get_elevations(locations)

            return tuple(
                ElevationSample(
                    point=sample.point,
                    distance_meters=sample.distance_meters + 1,
                    elevation_meters=sample.elevation_meters,
                )
                for sample in initial
            )

    result = _service(ShiftedProvider()).acquire_routes((_route(),))[0]

    assert result.unavailable_reason is TerrainUnavailableReason.INVALID_PROVIDER_RESPONSE


def test_wrong_coordinate_in_result_is_rejected() -> None:
    class WrongCoordinateProvider(FakeElevationProvider):
        def get_elevations(
            self,
            locations: Sequence[TerrainSampleLocation],
        ) -> tuple[ElevationSample, ...]:
            original = super().get_elevations(locations)

            return tuple(
                ElevationSample(
                    point=RoutePoint(0, 0),
                    distance_meters=sample.distance_meters,
                    elevation_meters=sample.elevation_meters,
                )
                for sample in original
            )

    result = _service(WrongCoordinateProvider()).acquire_routes((_route(),))[0]

    assert result.unavailable_reason is TerrainUnavailableReason.INVALID_PROVIDER_RESPONSE


def test_guard_enforces_five_requests_for_two_long_routes_without_losing_routes() -> None:
    clock = FakeClock()

    gate = PublicElevationCallGate(
        enabled=True,
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )

    provider = FakeElevationProvider()
    trip = gate.new_trip(provider)

    results = TerrainAcquisitionService(
        elevation_provider=trip,
        enabled=True,
    ).acquire_routes((_route(100_000), _route(100_000), _route(1_000)))

    assert [item.status for item in results] == [
        TerrainAcquisitionStatus.COMPLETE,
        TerrainAcquisitionStatus.PARTIAL,
        TerrainAcquisitionStatus.UNAVAILABLE,
    ]

    assert results[1].profile is not None
    assert results[1].profile.missing_sample_count == 56
    assert results[2].unavailable_reason is TerrainUnavailableReason.REQUEST_BUDGET_EXCEEDED
    assert trip.request_count == 5
    assert len(provider.calls) == 5


def test_guards_and_service_must_both_opt_in_to_live_calls() -> None:
    gate = PublicElevationCallGate(enabled=False)
    provider = FakeElevationProvider()

    results = TerrainAcquisitionService(
        elevation_provider=gate.new_trip(provider),
        enabled=True,
    ).acquire_routes((_route(),))

    assert results[0].status is TerrainAcquisitionStatus.UNAVAILABLE
    assert provider.calls == []


def test_route_objects_are_not_mutated() -> None:
    candidates = (_route(), _route(2_000))
    before = tuple(candidates)

    _service(FakeElevationProvider()).acquire_routes(candidates)

    assert candidates == before


@pytest.mark.parametrize("enabled", [1, None, "yes"])
def test_configuration_requires_boolean_enabled(enabled: object) -> None:
    with pytest.raises(TypeError, match="enabled"):
        TerrainAcquisitionService(
            elevation_provider=FakeElevationProvider(),
            enabled=enabled,  # type: ignore[arg-type]
        )


def test_geometry_fidelity_must_be_typed() -> None:
    with pytest.raises(TypeError, match="geometry_fidelity"):
        TerrainAcquisitionService(
            elevation_provider=FakeElevationProvider(),
            geometry_fidelity="overview",  # type: ignore[arg-type]
        )
