import httpx
import pytest

from routevalue.application.models import VehicleCatalogConfiguration
from routevalue.infrastructure.vehicles.fueleconomy_catalog import (
    FUEL_ECONOMY_SOURCE,
    FuelEconomyGovCatalog,
)
from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FUEL_ECONOMY_BASE_URL,
    FuelEconomyGovClient,
    FuelEconomyGovResponseError,
)


def test_catalog_lists_years_newest_first() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == (f"{FUEL_ECONOMY_BASE_URL}/vehicle/menu/year")

        return httpx.Response(
            status_code=200,
            content=b"""
                <menuItems>
                    <menuItem>
                        <text>2024</text>
                        <value>2024</value>
                    </menuItem>
                    <menuItem>
                        <text>2026</text>
                        <value>2026</value>
                    </menuItem>
                    <menuItem>
                        <text>2025</text>
                        <value>2025</value>
                    </menuItem>
                    <menuItem>
                        <text>2026</text>
                        <value>2026</value>
                    </menuItem>
                </menuItems>
            """,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        catalog = FuelEconomyGovCatalog(client=FuelEconomyGovClient(client=http_client))

        years = catalog.list_years()

    assert years == (
        2026,
        2025,
        2024,
    )


def test_catalog_lists_makes_in_deterministic_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/vehicle/menu/make")
        assert request.url.params["year"] == "2026"

        return httpx.Response(
            status_code=200,
            content=b"""
                <menuItems>
                    <menuItem>
                        <text>Toyota</text>
                        <value>Toyota</value>
                    </menuItem>
                    <menuItem>
                        <text>Acura</text>
                        <value>Acura</value>
                    </menuItem>
                    <menuItem>
                        <text>Honda</text>
                        <value>Honda</value>
                    </menuItem>
                    <menuItem>
                        <text>Toyota</text>
                        <value>Toyota</value>
                    </menuItem>
                </menuItems>
            """,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        catalog = FuelEconomyGovCatalog(client=FuelEconomyGovClient(client=http_client))

        makes = catalog.list_makes(year=2026)

    assert makes == (
        "Acura",
        "Honda",
        "Toyota",
    )


def test_catalog_lists_models_using_year_and_make() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/vehicle/menu/model")
        assert request.url.params["year"] == "2026"
        assert request.url.params["make"] == "Toyota"

        return httpx.Response(
            status_code=200,
            content=b"""
                <menuItems>
                    <menuItem>
                        <text>Corolla</text>
                        <value>Corolla</value>
                    </menuItem>
                    <menuItem>
                        <text>Camry</text>
                        <value>Camry</value>
                    </menuItem>
                </menuItems>
            """,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        catalog = FuelEconomyGovCatalog(client=FuelEconomyGovClient(client=http_client))

        models = catalog.list_models(
            year=2026,
            make="Toyota",
        )

    assert models == (
        "Camry",
        "Corolla",
    )


def test_catalog_lists_configurations_with_provider_provenance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/vehicle/menu/options")
        assert request.url.params["year"] == "2026"
        assert request.url.params["make"] == "Toyota"
        assert request.url.params["model"] == "Camry"

        return httpx.Response(
            status_code=200,
            content=b"""
                <menuItems>
                    <menuItem>
                        <text>2.5L 4cyl 8A (AWD)</text>
                        <value>50002</value>
                    </menuItem>
                    <menuItem>
                        <text>2.5L 4cyl 8A (FWD)</text>
                        <value>50001</value>
                    </menuItem>
                </menuItems>
            """,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        catalog = FuelEconomyGovCatalog(client=FuelEconomyGovClient(client=http_client))

        configurations = catalog.list_configurations(
            year=2026,
            make="Toyota",
            model="Camry",
        )

    assert configurations == (
        VehicleCatalogConfiguration(
            year=2026,
            make="Toyota",
            model="Camry",
            configuration="2.5L 4cyl 8A (AWD)",
            source=FUEL_ECONOMY_SOURCE,
            source_id="50002",
        ),
        VehicleCatalogConfiguration(
            year=2026,
            make="Toyota",
            model="Camry",
            configuration="2.5L 4cyl 8A (FWD)",
            source=FUEL_ECONOMY_SOURCE,
            source_id="50001",
        ),
    )


@pytest.mark.parametrize(
    (
        "response_content",
        "message",
    ),
    [
        (
            b"<vehicles />",
            "invalid root element",
        ),
        (
            b"""
                <menuItems>
                    <menuItem>
                        <value>Toyota</value>
                    </menuItem>
                </menuItems>
            """,
            "missing text",
        ),
        (
            b"""
                <menuItems>
                    <menuItem>
                        <text>Toyota</text>
                    </menuItem>
                </menuItems>
            """,
            "missing value",
        ),
        (
            b"""
                <menuItems>
                    <menuItem>
                        <text>   </text>
                        <value>Toyota</value>
                    </menuItem>
                </menuItems>
            """,
            "missing text",
        ),
        (
            b"""
                <menuItems>
                    <menuItem>
                        <text>Toyota</text>
                        <value>   </value>
                    </menuItem>
                </menuItems>
            """,
            "missing value",
        ),
    ],
)
def test_catalog_rejects_malformed_menu_structure(
    response_content: bytes,
    message: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=response_content,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        catalog = FuelEconomyGovCatalog(client=FuelEconomyGovClient(client=http_client))

        with pytest.raises(
            FuelEconomyGovResponseError,
            match=message,
        ):
            catalog.list_makes(year=2026)


@pytest.mark.parametrize(
    "year_value",
    [
        "unknown",
        "0",
        "-1",
    ],
)
def test_catalog_rejects_invalid_provider_year(
    year_value: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=f"""
                <menuItems>
                    <menuItem>
                        <text>{year_value}</text>
                        <value>{year_value}</value>
                    </menuItem>
                </menuItems>
            """.encode(),
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        catalog = FuelEconomyGovCatalog(client=FuelEconomyGovClient(client=http_client))

        with pytest.raises(
            FuelEconomyGovResponseError,
            match="invalid model year",
        ):
            catalog.list_years()


@pytest.mark.parametrize(
    "method_name",
    [
        "makes",
        "models",
        "configurations",
    ],
)
def test_catalog_rejects_nonpositive_requested_year_without_http_request(
    method_name: str,
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            status_code=200,
            content=b"<menuItems />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        catalog = FuelEconomyGovCatalog(client=FuelEconomyGovClient(client=http_client))

        with pytest.raises(
            ValueError,
            match="year must be greater than zero",
        ):
            if method_name == "makes":
                catalog.list_makes(year=0)
            elif method_name == "models":
                catalog.list_models(
                    year=0,
                    make="Toyota",
                )
            else:
                catalog.list_configurations(
                    year=0,
                    make="Toyota",
                    model="Camry",
                )

    assert request_count == 0


@pytest.mark.parametrize(
    (
        "make",
        "model",
        "message",
    ),
    [
        (
            "   ",
            None,
            "make cannot be blank",
        ),
        (
            "   ",
            "Camry",
            "make cannot be blank",
        ),
        (
            "Toyota",
            "   ",
            "model cannot be blank",
        ),
    ],
)
def test_catalog_rejects_blank_hierarchy_selection_without_http_request(
    make: str,
    model: str | None,
    message: str,
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            status_code=200,
            content=b"<menuItems />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        catalog = FuelEconomyGovCatalog(client=FuelEconomyGovClient(client=http_client))

        with pytest.raises(
            ValueError,
            match=message,
        ):
            if model is None:
                catalog.list_models(
                    year=2026,
                    make=make,
                )
            else:
                catalog.list_configurations(
                    year=2026,
                    make=make,
                    model=model,
                )

    assert request_count == 0


def test_catalog_allows_empty_year_menu() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=b"<menuItems />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        catalog = FuelEconomyGovCatalog(client=FuelEconomyGovClient(client=http_client))

        assert catalog.list_years() == ()


def test_catalog_allows_empty_make_menu() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=b"<menuItems />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        catalog = FuelEconomyGovCatalog(client=FuelEconomyGovClient(client=http_client))

        assert catalog.list_makes(year=2026) == ()


def test_catalog_allows_empty_model_menu() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=b"<menuItems />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        catalog = FuelEconomyGovCatalog(client=FuelEconomyGovClient(client=http_client))

        assert (
            catalog.list_models(
                year=2026,
                make="Toyota",
            )
            == ()
        )


def test_catalog_allows_empty_configuration_menu() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=b"<menuItems />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        catalog = FuelEconomyGovCatalog(client=FuelEconomyGovClient(client=http_client))

        assert (
            catalog.list_configurations(
                year=2026,
                make="Toyota",
                model="Camry",
            )
            == ()
        )
