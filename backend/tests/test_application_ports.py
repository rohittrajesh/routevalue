from collections.abc import Sequence
from decimal import Decimal

import pytest

from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteSearchRequest,
    VehicleCatalogConfiguration,
    VehicleSpecificationLookupResult,
    VehicleSpecificationUnavailableReason,
)
from routevalue.application.ports import (
    EnergyCostEstimator,
    RouteProvider,
    VehicleSpecificationProvider,
)
from routevalue.domain.models import (
    EnergyEstimate,
    GasolineGrade,
    GasolineVehicleSpecification,
    RouteCandidate,
)


class FakeRouteProvider:
    def __init__(self, routes: Sequence[ProvidedRoute]) -> None:
        self._routes = tuple(routes)
        self.requests: list[RouteSearchRequest] = []

    def get_routes(
        self,
        request: RouteSearchRequest,
    ) -> Sequence[ProvidedRoute]:
        self.requests.append(request)
        return self._routes


class FakeEnergyCostEstimator:
    def __init__(self, estimate: EnergyEstimate | None) -> None:
        self._estimate = estimate
        self.routes: list[RouteCandidate] = []

    def estimate_energy(
        self,
        route: RouteCandidate,
    ) -> EnergyEstimate | None:
        self.routes.append(route)
        return self._estimate


class FakeVehicleSpecificationProvider:
    def __init__(
        self,
        *,
        years: Sequence[int],
        makes: Sequence[str],
        models: Sequence[str],
        configurations: Sequence[VehicleCatalogConfiguration],
        specification_result: VehicleSpecificationLookupResult,
    ) -> None:
        self._years = tuple(years)
        self._makes = tuple(makes)
        self._models = tuple(models)
        self._configurations = tuple(configurations)
        self._specification_result = specification_result

        self.make_requests: list[int] = []
        self.model_requests: list[tuple[int, str]] = []
        self.configuration_requests: list[tuple[int, str, str]] = []
        self.specification_requests: list[VehicleCatalogConfiguration] = []

    def list_years(self) -> Sequence[int]:
        return self._years

    def list_makes(
        self,
        *,
        year: int,
    ) -> Sequence[str]:
        self.make_requests.append(year)
        return self._makes

    def list_models(
        self,
        *,
        year: int,
        make: str,
    ) -> Sequence[str]:
        self.model_requests.append((year, make))
        return self._models

    def list_configurations(
        self,
        *,
        year: int,
        make: str,
        model: str,
    ) -> Sequence[VehicleCatalogConfiguration]:
        self.configuration_requests.append((year, make, model))
        return self._configurations

    def get_specification(
        self,
        configuration: VehicleCatalogConfiguration,
    ) -> VehicleSpecificationLookupResult:
        self.specification_requests.append(configuration)
        return self._specification_result


def get_routes_from_provider(
    provider: RouteProvider,
    request: RouteSearchRequest,
) -> Sequence[ProvidedRoute]:
    return provider.get_routes(request)


def get_energy_estimate(
    estimator: EnergyCostEstimator,
    route: RouteCandidate,
) -> EnergyEstimate | None:
    return estimator.estimate_energy(route)


def get_vehicle_years(
    provider: VehicleSpecificationProvider,
) -> Sequence[int]:
    return provider.list_years()


def get_vehicle_makes(
    provider: VehicleSpecificationProvider,
    *,
    year: int,
) -> Sequence[str]:
    return provider.list_makes(year=year)


def get_vehicle_models(
    provider: VehicleSpecificationProvider,
    *,
    year: int,
    make: str,
) -> Sequence[str]:
    return provider.list_models(
        year=year,
        make=make,
    )


def get_vehicle_configurations(
    provider: VehicleSpecificationProvider,
    *,
    year: int,
    make: str,
    model: str,
) -> Sequence[VehicleCatalogConfiguration]:
    return provider.list_configurations(
        year=year,
        make=make,
        model=model,
    )


def get_vehicle_specification(
    provider: VehicleSpecificationProvider,
    configuration: VehicleCatalogConfiguration,
) -> VehicleSpecificationLookupResult:
    return provider.get_specification(configuration)


def _route_search_request() -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=ResolvedLocation(
            display_name="Origin",
            latitude=32.88,
            longitude=-117.23,
        ),
        destination=ResolvedLocation(
            display_name="Destination",
            latitude=32.88,
            longitude=-117.23,
        ),
    )


def _vehicle_configuration() -> VehicleCatalogConfiguration:
    return VehicleCatalogConfiguration(
        year=2026,
        make="Toyota",
        model="Camry",
        configuration="2.5L 4cyl CVT (FWD)",
        source="fueleconomy_gov",
        source_id="12345",
    )


def _vehicle_specification_result() -> VehicleSpecificationLookupResult:
    return VehicleSpecificationLookupResult(
        specification=GasolineVehicleSpecification(
            combined_mpg=Decimal("31.5"),
            fuel_grade=GasolineGrade.REGULAR,
        ),
        unavailable_reason=None,
    )


def _vehicle_provider() -> FakeVehicleSpecificationProvider:
    configuration = _vehicle_configuration()

    return FakeVehicleSpecificationProvider(
        years=(2025, 2026),
        makes=("Honda", "Toyota"),
        models=("Camry", "Corolla"),
        configurations=(configuration,),
        specification_result=_vehicle_specification_result(),
    )


def test_fake_route_provider_returns_controlled_routes_in_stable_order() -> None:
    first_route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    second_route = RouteCandidate(
        distance_meters=12_000,
        duration_seconds=800,
        toll_cost=Decimal("2.50"),
    )

    first_provided_route = ProvidedRoute(route=first_route)
    second_provided_route = ProvidedRoute(route=second_route)

    request = _route_search_request()

    provider = FakeRouteProvider(
        [
            first_provided_route,
            second_provided_route,
        ]
    )

    routes = get_routes_from_provider(provider, request)

    assert routes == (
        first_provided_route,
        second_provided_route,
    )
    assert provider.requests == [request]


@pytest.mark.parametrize(
    "display_name",
    [
        "",
        "   ",
    ],
)
def test_resolved_location_rejects_blank_display_name(
    display_name: str,
) -> None:
    with pytest.raises(ValueError, match="display_name cannot be blank"):
        ResolvedLocation(
            display_name=display_name,
            latitude=32.88,
            longitude=-117.23,
        )


@pytest.mark.parametrize(
    "estimate",
    [
        EnergyEstimate(cost=Decimal("1.25")),
        None,
    ],
)
def test_fake_energy_cost_estimator_returns_controlled_result(
    estimate: EnergyEstimate | None,
) -> None:
    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    estimator = FakeEnergyCostEstimator(estimate)

    result = get_energy_estimate(estimator, route)

    assert result == estimate
    assert estimator.routes == [route]


def test_fake_vehicle_specification_provider_returns_years_in_stable_order() -> None:
    provider = _vehicle_provider()

    years = get_vehicle_years(provider)

    assert years == (2025, 2026)


def test_fake_vehicle_specification_provider_receives_year_for_make_lookup() -> None:
    provider = _vehicle_provider()

    makes = get_vehicle_makes(
        provider,
        year=2026,
    )

    assert makes == ("Honda", "Toyota")
    assert provider.make_requests == [2026]


def test_fake_vehicle_specification_provider_receives_year_and_make_for_model_lookup() -> None:
    provider = _vehicle_provider()

    models = get_vehicle_models(
        provider,
        year=2026,
        make="Toyota",
    )

    assert models == ("Camry", "Corolla")
    assert provider.model_requests == [
        (
            2026,
            "Toyota",
        )
    ]


def test_fake_vehicle_specification_provider_returns_configurations_with_provenance() -> None:
    provider = _vehicle_provider()
    expected_configuration = _vehicle_configuration()

    configurations = get_vehicle_configurations(
        provider,
        year=2026,
        make="Toyota",
        model="Camry",
    )

    assert configurations == (expected_configuration,)
    assert provider.configuration_requests == [
        (
            2026,
            "Toyota",
            "Camry",
        )
    ]


def test_fake_vehicle_specification_provider_resolves_normalized_specification() -> None:
    provider = _vehicle_provider()
    configuration = _vehicle_configuration()

    result = get_vehicle_specification(
        provider,
        configuration,
    )

    assert result == _vehicle_specification_result()
    assert provider.specification_requests == [configuration]


def test_fake_vehicle_specification_provider_can_return_unavailable_outcome() -> None:
    configuration = _vehicle_configuration()
    unavailable_result = VehicleSpecificationLookupResult(
        specification=None,
        unavailable_reason=VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN,
    )
    provider = FakeVehicleSpecificationProvider(
        years=(2026,),
        makes=("Toyota",),
        models=("Prius",),
        configurations=(configuration,),
        specification_result=unavailable_result,
    )

    result = get_vehicle_specification(
        provider,
        configuration,
    )

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN
    assert provider.specification_requests == [configuration]
