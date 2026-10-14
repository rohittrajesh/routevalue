"""M8 bounded EIA XLS downloader tests with mocked HTTP transport."""

import httpx
import pytest

from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
)
from routevalue.infrastructure.pricing.eia_retrieval_models import (
    EiaRetrievalError,
    EiaRetrievalFailureReason,
    EiaRetrievalLimits,
)
from routevalue.infrastructure.pricing.eia_xls_downloader import (
    XLS_SIGNATURE,
    download_eia_xls_workbook,
)


def make_client(
    handler: httpx.MockTransport,
) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_california_workbook_download() -> None:
    content = XLS_SIGNATURE + b"california-test-payload"
    seen_urls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, content=content)

    with make_client(httpx.MockTransport(respond)) as client:
        result = download_eia_xls_workbook(
            region=EIA_CALIFORNIA_REGION,
            client=client,
        )

    assert result.content == content
    assert result.source_url == EIA_CALIFORNIA_REGION.workbook_url
    assert seen_urls == [EIA_CALIFORNIA_REGION.workbook_url]


def test_national_workbook_download() -> None:
    content = XLS_SIGNATURE + b"national-test-payload"

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    with make_client(httpx.MockTransport(respond)) as client:
        result = download_eia_xls_workbook(
            region=EIA_US_REGION,
            client=client,
        )

    assert result.content == content
    assert result.source_url == EIA_US_REGION.workbook_url


def test_download_does_not_follow_redirects() -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "https://example.com/workbook.xls"},
        )

    with (
        make_client(httpx.MockTransport(respond)) as client,
        pytest.raises(EiaRetrievalError) as exc,
    ):
        download_eia_xls_workbook(
            region=EIA_CALIFORNIA_REGION,
            client=client,
        )

    assert exc.value.reason is EiaRetrievalFailureReason.UNSAFE_REDIRECT
    assert exc.value.status_code == 302
    assert len(calls) == 1


@pytest.mark.parametrize("status_code", [403, 404, 429, 500, 503])
def test_http_errors_are_classified(status_code: int) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    with (
        make_client(httpx.MockTransport(respond)) as client,
        pytest.raises(EiaRetrievalError) as exc,
    ):
        download_eia_xls_workbook(
            region=EIA_CALIFORNIA_REGION,
            client=client,
        )

    assert exc.value.reason is EiaRetrievalFailureReason.HTTP_ERROR
    assert exc.value.status_code == status_code


def test_empty_response_is_rejected() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    with (
        make_client(httpx.MockTransport(respond)) as client,
        pytest.raises(EiaRetrievalError) as exc,
    ):
        download_eia_xls_workbook(
            region=EIA_CALIFORNIA_REGION,
            client=client,
        )

    assert exc.value.reason is EiaRetrievalFailureReason.EMPTY_RESPONSE


def test_invalid_xls_signature_is_rejected() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not a binary XLS file")

    with (
        make_client(httpx.MockTransport(respond)) as client,
        pytest.raises(EiaRetrievalError) as exc,
    ):
        download_eia_xls_workbook(
            region=EIA_US_REGION,
            client=client,
        )

    assert exc.value.reason is EiaRetrievalFailureReason.INVALID_CONTENT


def test_declared_oversized_response_is_rejected() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": "1000000"},
            content=XLS_SIGNATURE,
        )

    with (
        make_client(httpx.MockTransport(respond)) as client,
        pytest.raises(EiaRetrievalError) as exc,
    ):
        download_eia_xls_workbook(
            region=EIA_US_REGION,
            client=client,
            limits=EiaRetrievalLimits(max_download_bytes=1024),
        )

    assert exc.value.reason is EiaRetrievalFailureReason.DOWNLOAD_TOO_LARGE


def test_streamed_oversized_response_is_rejected() -> None:
    content = XLS_SIGNATURE + b"x" * 2000

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    with (
        make_client(httpx.MockTransport(respond)) as client,
        pytest.raises(EiaRetrievalError) as exc,
    ):
        download_eia_xls_workbook(
            region=EIA_US_REGION,
            client=client,
            limits=EiaRetrievalLimits(max_download_bytes=1024),
        )

    assert exc.value.reason is EiaRetrievalFailureReason.DOWNLOAD_TOO_LARGE


def test_exact_download_size_limit_is_accepted() -> None:
    content = XLS_SIGNATURE + b"x" * 100

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    with make_client(httpx.MockTransport(respond)) as client:
        result = download_eia_xls_workbook(
            region=EIA_US_REGION,
            client=client,
            limits=EiaRetrievalLimits(max_download_bytes=len(content)),
        )

    assert result.content == content


def test_network_error_is_classified() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "simulated connection failure",
            request=request,
        )

    with (
        make_client(httpx.MockTransport(respond)) as client,
        pytest.raises(EiaRetrievalError) as exc,
    ):
        download_eia_xls_workbook(
            region=EIA_US_REGION,
            client=client,
        )

    assert exc.value.reason is EiaRetrievalFailureReason.NETWORK_ERROR


def test_timeout_is_classified() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            "simulated timeout",
            request=request,
        )

    with (
        make_client(httpx.MockTransport(respond)) as client,
        pytest.raises(EiaRetrievalError) as exc,
    ):
        download_eia_xls_workbook(
            region=EIA_CALIFORNIA_REGION,
            client=client,
        )

    assert exc.value.reason is EiaRetrievalFailureReason.TIMEOUT


def test_invalid_region_is_rejected_before_request() -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=XLS_SIGNATURE)

    with (
        make_client(httpx.MockTransport(respond)) as client,
        pytest.raises(TypeError, match="EiaGasolineRegion"),
    ):
        download_eia_xls_workbook(
            region="california",  # type: ignore[arg-type]
            client=client,
        )

    assert calls == 0
