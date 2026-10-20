"""M6-E safety gates: no live requests and deterministic budget tests."""

from collections.abc import Sequence
from math import nan
from threading import Thread

import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import ElevationSample
from routevalue.application.terrain_batching import (
    MAX_ELEVATION_BATCH_SIZE,
    ElevationBatchPlan,
    plan_elevation_batches,
)
from routevalue.application.terrain_ports import ElevationProviderUnavailableError
from routevalue.application.terrain_sampling import TerrainSampleLocation
from routevalue.infrastructure.elevation.safety import (
    TERRAIN_LIVE_ENABLED_ENV,
    ElevationAccessDisabledError,
    ElevationDailyBudgetExceededError,
    ElevationTripBudgetExceededError,
    PublicElevationCallGate,
    PublicElevationPolicy,
    terrain_live_enabled,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.waits: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


class FakeElevationProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[TerrainSampleLocation, ...]] = []
        self.fail = fail

    def get_elevations(
        self, locations: Sequence[TerrainSampleLocation]
    ) -> tuple[ElevationSample, ...]:
        batch = tuple(locations)
        self.calls.append(batch)
        if self.fail:
            raise ElevationProviderUnavailableError("mock outage")
        return tuple(
            ElevationSample(
                point=location.point,
                distance_meters=location.distance_meters,
                elevation_meters=None,
            )
            for location in batch
        )


def _locations(n: int) -> tuple[TerrainSampleLocation, ...]:
    return tuple(
        TerrainSampleLocation(
            point=RoutePoint(latitude=32.88 + i * 0.00001, longitude=-117.23),
            distance_meters=i * 250,
        )
        for i in range(n)
    )


def _gate(
    clock: FakeClock,
    *,
    enabled: bool = True,
    policy: PublicElevationPolicy | None = None,
) -> PublicElevationCallGate:
    return PublicElevationCallGate(
        enabled=enabled,
        policy=policy,
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )


def test_default_settings_fail_closed() -> None:
    assert not terrain_live_enabled({})
    assert not terrain_live_enabled({TERRAIN_LIVE_ENABLED_ENV: "0"})
    assert terrain_live_enabled({TERRAIN_LIVE_ENABLED_ENV: "1"})
    assert PublicElevationCallGate().enabled is False


@pytest.mark.parametrize("raw", ["true", "TRUE", "yes", "", "2", " 1"])
def test_unsafe_enablement_values_are_rejected(raw: str) -> None:
    with pytest.raises(ValueError, match="exactly '0' or '1'"):
        terrain_live_enabled({TERRAIN_LIVE_ENABLED_ENV: raw})


def test_disabled_provider_makes_no_upstream_calls() -> None:
    delegate = FakeElevationProvider()
    guarded = _gate(FakeClock(), enabled=False).new_trip(delegate)
    with pytest.raises(ElevationAccessDisabledError):
        guarded.get_elevations(_locations(1))
    assert delegate.calls == []
    assert guarded.request_count == 0


def test_empty_batch_makes_no_request_or_reservation() -> None:
    delegate = FakeElevationProvider()
    guarded = _gate(FakeClock(), enabled=False).new_trip(delegate)
    assert guarded.get_elevations(()) == ()
    assert guarded.request_count == 0
    assert delegate.calls == []


def test_batch_planning_splits_256_into_100_100_56() -> None:
    places = _locations(256)
    plan = plan_elevation_batches(places)
    assert isinstance(plan, ElevationBatchPlan)
    assert MAX_ELEVATION_BATCH_SIZE == 100
    assert [len(batch) for batch in plan.batches] == [100, 100, 56]
    assert plan.request_count == 3
    assert plan.sample_count == 256
    assert tuple(point for batch in plan.batches for point in batch) == places


@pytest.mark.parametrize("count", [0, 1, 100, 101, 200, 201, 256])
def test_batch_planning_sizes(count: int) -> None:
    plan = plan_elevation_batches(_locations(count))
    assert plan.sample_count == count
    assert all(1 <= len(batch) <= 100 for batch in plan.batches)


def test_over_256_samples_are_rejected() -> None:
    with pytest.raises(ValueError, match="maximum route sample count"):
        plan_elevation_batches(_locations(257))


@pytest.mark.parametrize("limit", [0, -1, 101, True])
def test_invalid_batch_size_is_rejected(limit: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        plan_elevation_batches(_locations(1), max_batch_size=limit)


@pytest.mark.parametrize("limit", [0, -1, 257, True])
def test_invalid_sample_limit_is_rejected(limit: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        plan_elevation_batches(_locations(1), max_samples=limit)


def test_out_of_order_points_are_rejected_without_network() -> None:
    with pytest.raises(ValueError, match="strictly increase"):
        plan_elevation_batches(tuple(reversed(_locations(2))))


def test_nonfinite_coordinates_are_rejected_before_reservation() -> None:
    delegate = FakeElevationProvider()
    clock = FakeClock()
    trip = _gate(clock).new_trip(delegate)
    invalid = RoutePoint(latitude=0, longitude=0)
    object.__setattr__(invalid, "latitude", nan)
    point = TerrainSampleLocation(point=invalid, distance_meters=0)
    with pytest.raises(ValueError, match="finite"):
        trip.get_elevations((point,))
    assert trip.request_count == 0
    assert delegate.calls == []


def test_one_guarded_call_preserves_unknown_samples_without_fabricating_heights() -> None:
    delegate = FakeElevationProvider()
    trip = _gate(FakeClock()).new_trip(delegate)
    locations = _locations(2)
    result = trip.get_elevations(locations)
    assert tuple(item.distance_meters for item in result) == (0, 250)
    assert all(item.elevation_meters is None for item in result)
    assert trip.request_count == 1
    assert delegate.calls == [locations]


def test_guarded_provider_rejects_101_points_without_reservation() -> None:
    delegate = FakeElevationProvider()
    trip = _gate(FakeClock()).new_trip(delegate)
    with pytest.raises(ValueError, match="maximum route sample count"):
        trip.get_elevations(_locations(101))
    assert trip.request_count == 0
    assert delegate.calls == []


def test_five_request_limit_is_per_trip_across_multiple_batches() -> None:
    delegate = FakeElevationProvider()
    clock = FakeClock()
    trip = _gate(clock).new_trip(delegate)
    for _ in range(5):
        assert len(trip.get_elevations(_locations(1))) == 1
    with pytest.raises(ElevationTripBudgetExceededError):
        trip.get_elevations(_locations(1))
    assert trip.request_count == 5
    assert len(delegate.calls) == 5
    assert len(clock.waits) == 4


def test_call_failure_is_counted_without_retries() -> None:
    delegate = FakeElevationProvider(fail=True)
    trip = _gate(FakeClock()).new_trip(delegate)
    with pytest.raises(ElevationProviderUnavailableError, match="mock outage"):
        trip.get_elevations(_locations(1))
    assert trip.request_count == 1
    assert len(delegate.calls) == 1


def test_rate_gap_applies_across_distinct_trips() -> None:
    clock = FakeClock()
    gate = _gate(clock)
    left = gate.new_trip(FakeElevationProvider())
    right = gate.new_trip(FakeElevationProvider())
    left.get_elevations(_locations(1))
    right.get_elevations(_locations(1))
    assert clock.waits == pytest.approx([1.1])
    assert left.request_count == right.request_count == 1


def test_rolling_24_hour_budget_applies_across_trips() -> None:
    clock = FakeClock()
    gate = _gate(clock, policy=PublicElevationPolicy(max_requests_per_24_hours=2))
    for _ in range(2):
        gate.new_trip(FakeElevationProvider()).get_elevations(_locations(1))
    delegate = FakeElevationProvider()
    with pytest.raises(ElevationDailyBudgetExceededError):
        gate.new_trip(delegate).get_elevations(_locations(1))
    assert delegate.calls == []
    clock.now = 86_400.0
    assert len(gate.new_trip(delegate).get_elevations(_locations(1))) == 1


def test_budget_denial_does_not_count_trip_request() -> None:
    clock = FakeClock()
    gate = _gate(clock, policy=PublicElevationPolicy(max_requests_per_24_hours=1))
    trip = gate.new_trip(FakeElevationProvider())
    trip.get_elevations(_locations(1))
    with pytest.raises(ElevationDailyBudgetExceededError):
        trip.get_elevations(_locations(1))
    assert trip.request_count == 1


def test_backward_clock_fails_closed() -> None:
    clock = FakeClock()
    gate = _gate(clock)
    gate.reserve()
    clock.now = -1
    with pytest.raises(ValueError, match="backwards"):
        gate.reserve()


def test_nonadvancing_sleeper_fails_closed() -> None:
    clock = FakeClock()
    gate = PublicElevationCallGate(enabled=True, clock=clock.monotonic, sleeper=lambda _: None)
    gate.reserve()
    with pytest.raises(RuntimeError, match="clock did not advance"):
        gate.reserve()


def test_invalid_policy_cannot_raise_above_public_limits() -> None:
    with pytest.raises(ValueError, match="between 1 and 6"):
        PublicElevationPolicy(max_requests_per_trip=7)
    with pytest.raises(ValueError, match="between 1 and 900"):
        PublicElevationPolicy(max_requests_per_24_hours=901)
    with pytest.raises(ValueError, match="at least 1.1"):
        PublicElevationPolicy(minimum_interval_seconds=1.0)


def test_parallel_reservations_are_serialized_by_one_shared_gate() -> None:
    clock = FakeClock()
    gate = _gate(clock)
    successful: list[int] = []

    def worker(number: int) -> None:
        gate.reserve()
        successful.append(number)

    threads = [Thread(target=worker, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(successful) == [0, 1, 2, 3]
    assert clock.now == pytest.approx(3.3)
