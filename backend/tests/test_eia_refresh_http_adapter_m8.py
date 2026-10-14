"""M8 regression tests for the EIA refresh HTTP adapter.

Uses httpx.MockTransport. No real network or database access.
"""

from collections.abc import Callable

import httpx
import pytest

from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_refresh_http_adapter import (
    EiaWorkbookFetcher,
)
from routevalue.infrastructure.pricing.eia_retrieval_models import (
    EiaRetrievalError,
    EiaRetrievalLimits,
)

XLS_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
WORKBOOK_BYTES = XLS_SIGNATURE + b"\x00" * 64


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )


@pytest.mark.parametrize(
    "region",
    [EIA_CALIFORNIA_REGION, EIA_US_REGION],
)
def test_adapter_returns_validated_workbook_bytes(
    region: EiaGasolineRegion,
) -> None:
    requested_urls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            content=WORKBOOK_BYTES,
        )

    with make_client(respond) as client:
        fetcher = EiaWorkbookFetcher(client=client)

        actual = fetcher(region)

        assert actual == WORKBOOK_BYTES
        assert requested_urls == [region.workbook_url]
        assert client.is_closed is False

    assert client.is_closed is True


def test_adapter_preserves_download_size_limit() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=WORKBOOK_BYTES,
        )

    limits = EiaRetrievalLimits(
        max_download_bytes=16,
    )

    with make_client(respond) as client:
        fetcher = EiaWorkbookFetcher(
            client=client,
            limits=limits,
        )

        with pytest.raises(EiaRetrievalError):
            fetcher(EIA_US_REGION)


def test_adapter_rejects_redirects() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"Location": "https://example.com/file.xls"},
        )

    with make_client(respond) as client:
        fetcher = EiaWorkbookFetcher(client=client)

        with pytest.raises(EiaRetrievalError):
            fetcher(EIA_CALIFORNIA_REGION)


def test_adapter_preserves_http_failures() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with make_client(respond) as client:
        fetcher = EiaWorkbookFetcher(client=client)

        with pytest.raises(EiaRetrievalError):
            fetcher(EIA_US_REGION)


def test_adapter_rejects_invalid_xls_content() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not an XLS workbook",
        )

    with make_client(respond) as client:
        fetcher = EiaWorkbookFetcher(client=client)

        with pytest.raises(EiaRetrievalError):
            fetcher(EIA_CALIFORNIA_REGION)


def test_adapter_rejects_invalid_client() -> None:
    with pytest.raises(
        TypeError,
        match="httpx.Client",
    ):
        EiaWorkbookFetcher(
            client=None,  # type: ignore[arg-type]
        )
