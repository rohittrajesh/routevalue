from decimal import Decimal

import httpx
import pytest

from routevalue.application.models import (
    VehicleCatalogConfiguration,
    VehicleSpecificationUnavailableReason,
)
from routevalue.application.ports import VehicleSpecificationProvider
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
)
from routevalue.infrastructure.vehicles.fueleconomy_catalog import (
    FUEL_ECONOMY_SOURCE,
)
from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FuelEconomyGovClient,
    FuelEconomyGovHTTPError,
    FuelEconomyGovResponseError,
)
from routevalue.infrastructure.vehicles.fueleconomy_provider import (
    FuelEconomyGovVehicleSpecificationProvider,
)


def _configuration(
    *,
    source: str = FUEL_ECONOMY_SOURCE,
    source_id: str = "12345",
) -> VehicleCatalogConfiguration:
    return VehicleCatalogConfiguration(
        year=2026,
        make="Example",
        model="Example Model",
        configuration="Example Configuration",
        source=source,
        source_id=source_id,
    )


def _as_vehicle_specification_provider(
    provider: VehicleSpecificationProvider,
) -> VehicleSpecificationProvider:
    return provider


def test_fueleconomy_provider_satisfies_complete_application_port() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path.endswith("/vehicle/menu/year"):
            return httpx.Response(
                status_code=200,
                content=b"""
                    <menuItems>
                        <menuItem>
                            <text>2026</text>
                            <value>2026</value>
                        </menuItem>
                    </menuItems>
                """,
            )

        if path.endswith("/vehicle/menu/make"):
            assert request.url.params["year"] == "2026"

            return httpx.Response(
                status_code=200,
                content=b"""
                    <menuItems>
                        <menuItem>
                            <text>Example</text>
                            <value>Example</value>
                        </menuItem>
                    </menuItems>
                """,
            )

        if path.endswith("/vehicle/menu/model"):
            assert request.url.params["year"] == "2026"
            assert request.url.params["make"] == "Example"

            return httpx.Response(
                status_code=200,
                content=b"""
                    <menuItems>
                        <menuItem>
                            <text>Example Model</text>
                            <value>Example Model</value>
                        </menuItem>
                    </menuItems>
                """,
            )

        if path.endswith("/vehicle/menu/options"):
            assert request.url.params["year"] == "2026"
            assert request.url.params["make"] == "Example"
            assert request.url.params["model"] == "Example Model"

            return httpx.Response(
                status_code=200,
                content=b"""
                    <menuItems>
                        <menuItem>
                            <text>Example Configuration</text>
                            <value>12345</value>
                        </menuItem>
                    </menuItems>
                """,
            )

        if path.endswith("/vehicle/12345"):
            return httpx.Response(
                status_code=200,
                content=b"""
                    <vehicle>
                        <id>12345</id>
                        <fuelType1>Regular Gasoline</fuelType1>
                        <city08>28</city08>
                        <highway08>39</highway08>
                        <comb08>32</comb08>
                    </vehicle>
                """,
            )

        raise AssertionError(f"unexpected request path: {path}")

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        provider = _as_vehicle_specification_provider(
            FuelEconomyGovVehicleSpecificationProvider(
                client=FuelEconomyGovClient(client=http_client),
            )
        )

        years = tuple(provider.list_years())
        makes = tuple(provider.list_makes(year=2026))
        models = tuple(
            provider.list_models(
                year=2026,
                make="Example",
            )
        )
        configurations = tuple(
            provider.list_configurations(
                year=2026,
                make="Example",
                model="Example Model",
            )
        )
        result = provider.get_specification(configurations[0])

    assert years == (2026,)
    assert makes == ("Example",)
    assert models == ("Example Model",)
    assert configurations == (_configuration(),)

    assert result.specification == GasolineVehicleSpecification(
        city_mpg=Decimal(28),
        highway_mpg=Decimal(39),
        combined_mpg=Decimal(32),
        fuel_grade=GasolineGrade.REGULAR,
    )
    assert result.unavailable_reason is None


def test_fueleconomy_provider_resolves_battery_electric_vehicle() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/vehicle/12345")

        return httpx.Response(
            status_code=200,
            content=b"""
                <vehicle>
                    <id>12345</id>
                    <atvType>EV</atvType>
                    <fuelType1>Electricity</fuelType1>
                    <cityE>26</cityE>
                    <highwayE>31</highwayE>
                    <combE>28.5</combE>
                </vehicle>
            """,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        provider = FuelEconomyGovVehicleSpecificationProvider(
            client=FuelEconomyGovClient(client=http_client),
        )

        result = provider.get_specification(_configuration())

    assert result.specification == ElectricVehicleSpecification(
        city_kwh_per_mile=Decimal("0.26"),
        highway_kwh_per_mile=Decimal("0.31"),
        combined_kwh_per_mile=Decimal("0.285"),
    )
    assert result.unavailable_reason is None


@pytest.mark.parametrize(
    "advanced_vehicle_type",
    [
        "Plug-in Hybrid",
        "FFV",
        "Diesel",
        "CNG",
        "Bifuel (CNG)",
        "Bifuel (LPG)",
    ],
)
def test_fueleconomy_provider_returns_unsupported_powertrain(
    advanced_vehicle_type: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=f"""
                <vehicle>
                    <id>12345</id>
                    <atvType>{advanced_vehicle_type}</atvType>
                    <fuelType1>Regular Gasoline</fuelType1>
                    <city08>40</city08>
                    <highway08>38</highway08>
                    <comb08>39</comb08>
                </vehicle>
            """.encode(),
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        provider = FuelEconomyGovVehicleSpecificationProvider(
            client=FuelEconomyGovClient(client=http_client),
        )

        result = provider.get_specification(_configuration())

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN


def test_fueleconomy_provider_returns_missing_required_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=b"""
                <vehicle>
                    <id>12345</id>
                    <fuelType1>Regular Gasoline</fuelType1>
                    <city08>28</city08>
                    <highway08>39</highway08>
                </vehicle>
            """,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        provider = FuelEconomyGovVehicleSpecificationProvider(
            client=FuelEconomyGovClient(client=http_client),
        )

        result = provider.get_specification(_configuration())

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA


def test_fueleconomy_provider_maps_unknown_vehicle_id_to_not_found() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            status_code=404,
            content=b"<error />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        provider = FuelEconomyGovVehicleSpecificationProvider(
            client=FuelEconomyGovClient(client=http_client),
        )

        result = provider.get_specification(_configuration())

    assert request_count == 1
    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.NOT_FOUND


@pytest.mark.parametrize(
    "source_id",
    [
        "abc",
        "12.5",
        "-1",
        "0",
        "../vehicle/12345",
    ],
)
def test_fueleconomy_provider_rejects_invalid_local_vehicle_id_without_http_request(
    source_id: str,
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            status_code=200,
            content=b"<vehicle />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        provider = FuelEconomyGovVehicleSpecificationProvider(
            client=FuelEconomyGovClient(client=http_client),
        )

        result = provider.get_specification(
            _configuration(
                source_id=source_id,
            )
        )

    assert request_count == 0
    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.NOT_FOUND


def test_fueleconomy_provider_rejects_foreign_configuration_source_without_http_request() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            status_code=200,
            content=b"<vehicle />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        provider = FuelEconomyGovVehicleSpecificationProvider(
            client=FuelEconomyGovClient(client=http_client),
        )

        with pytest.raises(
            ValueError,
            match="source must match FuelEconomy.gov",
        ):
            provider.get_specification(
                _configuration(
                    source="another_provider",
                )
            )

    assert request_count == 0


def test_fueleconomy_provider_does_not_swallow_non_not_found_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=403,
            content=b"<error />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        provider = FuelEconomyGovVehicleSpecificationProvider(
            client=FuelEconomyGovClient(client=http_client),
        )

        with pytest.raises(FuelEconomyGovHTTPError) as exc_info:
            provider.get_specification(_configuration())

    assert exc_info.value.status_code == 403


def test_fueleconomy_provider_rejects_malformed_vehicle_root() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=b"""
                <menuItems>
                    <id>12345</id>
                </menuItems>
            """,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        provider = FuelEconomyGovVehicleSpecificationProvider(
            client=FuelEconomyGovClient(client=http_client),
        )

        with pytest.raises(
            FuelEconomyGovResponseError,
            match="invalid root element",
        ):
            provider.get_specification(_configuration())


def test_fueleconomy_provider_rejects_missing_response_vehicle_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=b"""
                <vehicle>
                    <fuelType1>Regular Gasoline</fuelType1>
                    <city08>28</city08>
                    <highway08>39</highway08>
                    <comb08>32</comb08>
                </vehicle>
            """,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        provider = FuelEconomyGovVehicleSpecificationProvider(
            client=FuelEconomyGovClient(client=http_client),
        )

        with pytest.raises(
            FuelEconomyGovResponseError,
            match="missing vehicle id",
        ):
            provider.get_specification(_configuration())


def test_fueleconomy_provider_rejects_mismatched_response_vehicle_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=b"""
                <vehicle>
                    <id>99999</id>
                    <fuelType1>Regular Gasoline</fuelType1>
                    <city08>28</city08>
                    <highway08>39</highway08>
                    <comb08>32</comb08>
                </vehicle>
            """,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        provider = FuelEconomyGovVehicleSpecificationProvider(
            client=FuelEconomyGovClient(client=http_client),
        )

        with pytest.raises(
            FuelEconomyGovResponseError,
            match="does not match requested vehicle",
        ):
            provider.get_specification(_configuration())
