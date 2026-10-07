import httpx
import pytest

from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FUEL_ECONOMY_BASE_URL,
    FUEL_ECONOMY_TIMEOUT_SECONDS,
    FuelEconomyGovClient,
    FuelEconomyGovHTTPError,
    FuelEconomyGovResponseError,
    FuelEconomyGovTransportError,
)


def test_fuel_economy_client_gets_and_parses_xml() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == (f"{FUEL_ECONOMY_BASE_URL}/vehicle/menu/make?year=2026")
        assert request.headers["Accept"] == "application/xml"

        assert request.extensions["timeout"] == {
            "connect": FUEL_ECONOMY_TIMEOUT_SECONDS,
            "read": FUEL_ECONOMY_TIMEOUT_SECONDS,
            "write": FUEL_ECONOMY_TIMEOUT_SECONDS,
            "pool": FUEL_ECONOMY_TIMEOUT_SECONDS,
        }

        return httpx.Response(
            status_code=200,
            content=b"""
                <menuItems>
                    <menuItem>
                        <text>Toyota</text>
                        <value>Toyota</value>
                    </menuItem>
                </menuItems>
            """,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        client = FuelEconomyGovClient(client=http_client)

        root = client.get_xml(
            "/vehicle/menu/make",
            params={
                "year": "2026",
            },
        )

    assert root.tag == "menuItems"
    assert root.findtext("./menuItem/text") == "Toyota"
    assert root.findtext("./menuItem/value") == "Toyota"


@pytest.mark.parametrize(
    "path",
    [
        "",
        "   ",
    ],
)
def test_fuel_economy_client_rejects_blank_path(path: str) -> None:
    with httpx.Client() as http_client:
        client = FuelEconomyGovClient(client=http_client)

        with pytest.raises(
            ValueError,
            match="path cannot be blank",
        ):
            client.get_xml(path)


def test_fuel_economy_client_retries_transport_failures_then_succeeds() -> None:
    request_count = 0
    sleep_delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        if request_count < 3:
            raise httpx.ConnectError(
                "connection failed",
                request=request,
            )

        return httpx.Response(
            status_code=200,
            content=b"<menuItems />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        client = FuelEconomyGovClient(
            client=http_client,
            sleeper=sleep_delays.append,
        )

        root = client.get_xml("/vehicle/menu/year")

    assert root.tag == "menuItems"
    assert request_count == 3
    assert sleep_delays == [
        0.25,
        0.5,
    ]


def test_fuel_economy_client_raises_after_transport_retries_exhausted() -> None:
    request_count = 0
    sleep_delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        raise httpx.ConnectError(
            "connection failed",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        client = FuelEconomyGovClient(
            client=http_client,
            sleeper=sleep_delays.append,
        )

        with pytest.raises(
            FuelEconomyGovTransportError,
            match="request failed",
        ):
            client.get_xml("/vehicle/menu/year")

    assert request_count == 3
    assert sleep_delays == [
        0.25,
        0.5,
    ]


def test_fuel_economy_client_retries_rate_limit_then_succeeds() -> None:
    request_count = 0
    sleep_delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        if request_count == 1:
            return httpx.Response(
                status_code=429,
                content=b"<error />",
            )

        return httpx.Response(
            status_code=200,
            content=b"<menuItems />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        client = FuelEconomyGovClient(
            client=http_client,
            sleeper=sleep_delays.append,
        )

        root = client.get_xml("/vehicle/menu/year")

    assert root.tag == "menuItems"
    assert request_count == 2
    assert sleep_delays == [0.25]


@pytest.mark.parametrize(
    "status_code",
    [
        500,
        502,
        503,
    ],
)
def test_fuel_economy_client_retries_server_errors(
    status_code: int,
) -> None:
    request_count = 0
    sleep_delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        if request_count == 1:
            return httpx.Response(
                status_code=status_code,
                content=b"<error />",
            )

        return httpx.Response(
            status_code=200,
            content=b"<menuItems />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        client = FuelEconomyGovClient(
            client=http_client,
            sleeper=sleep_delays.append,
        )

        root = client.get_xml("/vehicle/menu/year")

    assert root.tag == "menuItems"
    assert request_count == 2
    assert sleep_delays == [0.25]


def test_fuel_economy_client_raises_http_error_after_server_retries() -> None:
    request_count = 0
    sleep_delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            status_code=503,
            content=b"<error />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        client = FuelEconomyGovClient(
            client=http_client,
            sleeper=sleep_delays.append,
        )

        with pytest.raises(FuelEconomyGovHTTPError) as exc_info:
            client.get_xml("/vehicle/menu/year")

    assert exc_info.value.status_code == 503
    assert request_count == 3
    assert sleep_delays == [
        0.25,
        0.5,
    ]


def test_fuel_economy_client_does_not_retry_permanent_http_error() -> None:
    request_count = 0
    sleep_delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            status_code=404,
            content=b"<error />",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        client = FuelEconomyGovClient(
            client=http_client,
            sleeper=sleep_delays.append,
        )

        with pytest.raises(FuelEconomyGovHTTPError) as exc_info:
            client.get_xml("/vehicle/does-not-exist")

    assert exc_info.value.status_code == 404
    assert request_count == 1
    assert sleep_delays == []


def test_fuel_economy_client_rejects_malformed_successful_xml() -> None:
    request_count = 0
    sleep_delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            status_code=200,
            content=b"<menuItems>",
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        client = FuelEconomyGovClient(
            client=http_client,
            sleeper=sleep_delays.append,
        )

        with pytest.raises(
            FuelEconomyGovResponseError,
            match="not valid XML",
        ):
            client.get_xml("/vehicle/menu/year")

    assert request_count == 1
    assert sleep_delays == []
