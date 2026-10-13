"""M6-G regression tests proving terrain acquisition cannot alter M5 behavior."""

import json
from collections.abc import Sequence
from decimal import Decimal

from routevalue.api.mappers import to_trip_evaluation_response
from routevalue.api.v2_evaluation_mappers import (
    to_v2_trip_evaluation_response,
)
from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteGeometry,
    RoutePoint,
    RouteSearchRequest,
    TripEvaluationResult,
)
from routevalue.application.ports import EnergyCostEstimator
from routevalue.application.terrain import (
    ElevationSample,
    GeometryFidelity,
    TerrainAcquisitionResult,
    TerrainAcquisitionStatus,
    TerrainUnavailableReason,
)
from routevalue.application.terrain_acquisition import (
    TerrainAcquisitionService,
)
from routevalue.application.terrain_ports import (
    ElevationProviderUnavailableError,
)
from routevalue.application.terrain_sampling import (
    TerrainSampleLocation,
)
from routevalue.application.trip_evaluation import (
    TripEvaluationOrchestrator,
)
from routevalue.domain.models import (
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
    GasolineVehicleProfile,
    RouteCandidate,
)
from routevalue.infrastructure.energy.electric import (
    ElectricEnergyCostEstimator,
)
from routevalue.infrastructure.energy.gasoline import (
    GasolineEnergyCostEstimator,
)
from routevalue.main import create_app


class StaticRouteProvider:
    """Return one immutable set of normalized routes."""

    def __init__(
        self,
        routes: Sequence[ProvidedRoute],
    ) -> None:
        self.routes = tuple(routes)
        self.calls = 0

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> tuple[ProvidedRoute, ...]:
        del request

        self.calls += 1

        return self.routes


class DeterministicElevationProvider:
    """Provide predictable elevations without external HTTP."""

    def __init__(
        self,
        *,
        missing_offsets: frozenset[int] = frozenset(),
        fail: bool = False,
    ) -> None:
        self.missing_offsets = missing_offsets
        self.fail = fail
        self.calls: list[tuple[TerrainSampleLocation, ...]] = []

    def get_elevations(
        self,
        locations: Sequence[TerrainSampleLocation],
    ) -> tuple[ElevationSample, ...]:
        batch = tuple(locations)

        self.calls.append(batch)

        if self.fail:
            raise ElevationProviderUnavailableError("mock terrain outage")

        return tuple(
            ElevationSample(
                point=location.point,
                distance_meters=(location.distance_meters),
                elevation_meters=(
                    None
                    if location.distance_meters in self.missing_offsets
                    else Decimal(location.distance_meters) / Decimal(100)
                ),
            )
            for location in batch
        )


def _request() -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=ResolvedLocation(
            display_name="Origin",
            latitude=32.88,
            longitude=-117.23,
        ),
        destination=ResolvedLocation(
            display_name="Destination",
            latitude=32.73,
            longitude=-117.16,
        ),
    )


def _routes() -> tuple[
    ProvidedRoute,
    ...,
]:
    return (
        ProvidedRoute(
            route=RouteCandidate(
                distance_meters=10_000,
                duration_seconds=1_200,
                toll_cost=Decimal(0),
            ),
            geometry=RouteGeometry(
                points=(
                    RoutePoint(
                        latitude=32.88,
                        longitude=-117.23,
                    ),
                    RoutePoint(
                        latitude=32.81,
                        longitude=-117.20,
                    ),
                    RoutePoint(
                        latitude=32.73,
                        longitude=-117.16,
                    ),
                )
            ),
        ),
        ProvidedRoute(
            route=RouteCandidate(
                distance_meters=12_000,
                duration_seconds=900,
                toll_cost=Decimal("2.00"),
            ),
            geometry=RouteGeometry(
                points=(
                    RoutePoint(
                        latitude=32.88,
                        longitude=-117.23,
                    ),
                    RoutePoint(
                        latitude=32.79,
                        longitude=-117.18,
                    ),
                    RoutePoint(
                        latitude=32.73,
                        longitude=-117.16,
                    ),
                )
            ),
        ),
    )


def _gasoline_estimator() -> GasolineEnergyCostEstimator:
    return GasolineEnergyCostEstimator(
        vehicle=GasolineVehicleProfile(
            fuel_efficiency_mpg=Decimal(25),
            fuel_grade=GasolineGrade.REGULAR,
        ),
        fuel_price_quote=GasolinePriceQuote(
            price_per_gallon=Decimal(4),
            fuel_grade=GasolineGrade.REGULAR,
            source=(GasolinePriceSource.USER_OVERRIDE),
            observed_at=None,
        ),
    )


def _electric_estimator() -> ElectricEnergyCostEstimator:
    return ElectricEnergyCostEstimator(
        vehicle=ElectricVehicleSpecification(
            combined_kwh_per_mile=(Decimal("0.30")),
        ),
        electricity_price_quote=(
            ElectricityPriceQuote(
                price_per_kilowatt_hour=(Decimal("0.25")),
            )
        ),
    )


def _evaluate(
    routes: Sequence[ProvidedRoute],
    estimator: EnergyCostEstimator,
) -> TripEvaluationResult:
    return TripEvaluationOrchestrator(
        route_provider=StaticRouteProvider(routes),
        energy_cost_estimator=estimator,
    ).evaluate_trip(
        _request(),
        value_of_time_per_hour=Decimal(20),
    )


def _terrain(
    routes: Sequence[ProvidedRoute],
    provider: DeterministicElevationProvider,
) -> tuple[
    TerrainAcquisitionResult,
    ...,
]:
    return TerrainAcquisitionService(
        elevation_provider=provider,
        enabled=True,
        geometry_fidelity=(GeometryFidelity.SIMPLIFIED),
    ).acquire_routes(routes)


def test_complete_terrain_does_not_change_gasoline_evaluation() -> None:
    routes = _routes()

    before = _evaluate(
        routes,
        _gasoline_estimator(),
    )

    terrain = _terrain(
        routes,
        DeterministicElevationProvider(),
    )

    after = _evaluate(
        routes,
        _gasoline_estimator(),
    )

    assert all(result.status is TerrainAcquisitionStatus.COMPLETE for result in terrain)

    assert after == before


def test_complete_terrain_does_not_change_electric_evaluation() -> None:
    routes = _routes()

    before = _evaluate(
        routes,
        _electric_estimator(),
    )

    terrain = _terrain(
        routes,
        DeterministicElevationProvider(),
    )

    after = _evaluate(
        routes,
        _electric_estimator(),
    )

    assert all(result.status is TerrainAcquisitionStatus.COMPLETE for result in terrain)

    assert after == before


def test_partial_terrain_does_not_change_gasoline_evaluation() -> None:
    routes = _routes()

    before = _evaluate(
        routes,
        _gasoline_estimator(),
    )

    terrain = _terrain(
        routes,
        DeterministicElevationProvider(
            missing_offsets=frozenset({500}),
        ),
    )

    after = _evaluate(
        routes,
        _gasoline_estimator(),
    )

    assert all(result.status is TerrainAcquisitionStatus.PARTIAL for result in terrain)

    assert after == before


def test_provider_failure_does_not_change_electric_evaluation() -> None:
    routes = _routes()

    before = _evaluate(
        routes,
        _electric_estimator(),
    )

    terrain = _terrain(
        routes,
        DeterministicElevationProvider(fail=True),
    )

    after = _evaluate(
        routes,
        _electric_estimator(),
    )

    assert all(
        result.unavailable_reason is TerrainUnavailableReason.PROVIDER_UNAVAILABLE
        for result in terrain
    )

    assert after == before


def test_missing_terrain_does_not_set_decision_missing_data() -> None:
    routes = _routes()

    terrain = _terrain(
        routes,
        DeterministicElevationProvider(fail=True),
    )

    evaluation = _evaluate(
        routes,
        _gasoline_estimator(),
    )

    assert all(result.status is TerrainAcquisitionStatus.UNAVAILABLE for result in terrain)

    assert evaluation.decision.missing_data_present is False

    assert evaluation.decision.eligible_count == 2

    assert evaluation.decision.candidate_count == 2


def test_missing_geometry_does_not_make_route_ineligible() -> None:
    original = _routes()

    routes = (
        ProvidedRoute(
            route=original[0].route,
            geometry=None,
        ),
        original[1],
    )

    terrain = _terrain(
        routes,
        DeterministicElevationProvider(),
    )

    evaluation = _evaluate(
        routes,
        _electric_estimator(),
    )

    assert terrain[0].unavailable_reason is TerrainUnavailableReason.MISSING_GEOMETRY

    assert terrain[1].status is TerrainAcquisitionStatus.COMPLETE

    assert evaluation.route_evaluations[0].eligibility.eligible

    assert evaluation.route_evaluations[1].eligibility.eligible

    assert evaluation.decision.eligible_count == 2


def test_terrain_results_preserve_candidate_order_and_count() -> None:
    routes = _routes()

    terrain = _terrain(
        routes,
        DeterministicElevationProvider(),
    )

    assert tuple(result.route_index for result in terrain) == (0, 1)

    assert len(terrain) == len(routes)

    assert terrain[0].profile is not None
    assert terrain[1].profile is not None

    assert terrain[0].profile.route_distance_meters == 10_000

    assert terrain[1].profile.route_distance_meters == 12_000


def test_equal_route_values_with_distinct_geometry_remain_distinct() -> None:
    candidate = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=1_000,
        toll_cost=Decimal(0),
    )

    first_geometry = RouteGeometry(
        points=(
            RoutePoint(
                32.88,
                -117.23,
            ),
            RoutePoint(
                32.73,
                -117.16,
            ),
        )
    )

    second_geometry = RouteGeometry(
        points=(
            RoutePoint(
                32.88,
                -117.23,
            ),
            RoutePoint(
                32.80,
                -117.10,
            ),
            RoutePoint(
                32.73,
                -117.16,
            ),
        )
    )

    routes = (
        ProvidedRoute(
            route=candidate,
            geometry=first_geometry,
        ),
        ProvidedRoute(
            route=candidate,
            geometry=second_geometry,
        ),
    )

    terrain = _terrain(
        routes,
        DeterministicElevationProvider(),
    )

    evaluation = _evaluate(
        routes,
        _gasoline_estimator(),
    )

    assert tuple(result.route_index for result in terrain) == (0, 1)

    assert terrain[0].profile is not None
    assert terrain[1].profile is not None

    assert terrain[0].profile.samples[-1].point == first_geometry.points[-1]

    assert terrain[1].profile.samples[-1].point == second_geometry.points[-1]

    assert evaluation.decision.candidate_count == 2


def test_v2_mapper_does_not_expose_terrain() -> None:
    routes = _routes()

    _terrain(
        routes,
        DeterministicElevationProvider(),
    )

    evaluation = _evaluate(
        routes,
        _electric_estimator(),
    )

    payload = to_v2_trip_evaluation_response(evaluation).model_dump()

    route_payload = payload["route_evaluations"][0]

    assert set(route_payload) == {
        "route",
        "energy_estimate",
        "eligibility",
        "cost_breakdown",
        "geometry",
    }

    assert (
        "terrain"
        not in json.dumps(
            payload,
            default=str,
        ).lower()
    )


def test_v1_mapper_does_not_expose_terrain() -> None:
    routes = _routes()

    _terrain(
        routes,
        DeterministicElevationProvider(),
    )

    evaluation = _evaluate(
        routes,
        _gasoline_estimator(),
    )

    payload = to_trip_evaluation_response(evaluation).model_dump()

    route_payload = payload["route_evaluations"][0]

    assert set(route_payload) == {
        "route",
        "energy_estimate",
        "eligibility",
        "cost_breakdown",
        "geometry",
    }

    assert (
        "terrain"
        not in json.dumps(
            payload,
            default=str,
        ).lower()
    )


def test_openapi_v1_and_v2_success_contracts_do_not_contain_terrain() -> None:
    openapi = create_app().openapi()

    schemas = openapi["components"]["schemas"]

    v1_route_schema = schemas["RouteEvaluationResponse"]

    v2_route_schema = schemas["V2RouteEvaluationResponse"]

    assert "terrain" not in json.dumps(v1_route_schema).lower()

    assert "terrain" not in json.dumps(v2_route_schema).lower()


def test_terrain_acquisition_does_not_mutate_routes_or_decision() -> None:
    routes = _routes()

    original_routes = tuple(routes)

    before = _evaluate(
        routes,
        _gasoline_estimator(),
    )

    _terrain(
        routes,
        DeterministicElevationProvider(
            missing_offsets=frozenset(
                {
                    250,
                    500,
                }
            ),
        ),
    )

    after = _evaluate(
        routes,
        _gasoline_estimator(),
    )

    assert routes == original_routes

    assert after.decision == before.decision

    assert after.route_evaluations == before.route_evaluations
