"""Bounded HTTP retrieval of official EIA weekly gasoline XLS workbooks.

This module downloads raw bytes only. Workbook parsing, normalization,
freshness checks, cache updates, and refresh scheduling belong elsewhere.
"""

import httpx

from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_retrieval_models import (
    EiaDownloadedWorkbook,
    EiaRetrievalError,
    EiaRetrievalFailureReason,
    EiaRetrievalLimits,
)

# Legacy binary XLS files use the OLE Compound File signature.
XLS_SIGNATURE = bytes.fromhex("D0 CF 11 E0 A1 B1 1A E1")

DOWNLOAD_CHUNK_BYTES = 64 * 1024


def _trusted_workbook_url(region: EiaGasolineRegion) -> str:
    """Resolve only the exact approved EIA gasoline workbook URLs."""

    if not isinstance(region, EiaGasolineRegion):
        raise TypeError("region must be an EiaGasolineRegion")

    trusted_urls = frozenset(
        (
            EIA_CALIFORNIA_REGION.workbook_url,
            EIA_US_REGION.workbook_url,
        )
    )

    if region not in (EIA_CALIFORNIA_REGION, EIA_US_REGION):
        raise ValueError("region is not an approved EIA workbook region")

    url = region.workbook_url

    if url not in trusted_urls or not url.startswith("https://www.eia.gov/"):
        raise ValueError("untrusted EIA workbook URL")

    return url


def download_eia_xls_workbook(
    *,
    region: EiaGasolineRegion,
    client: httpx.Client,
    limits: EiaRetrievalLimits | None = None,
) -> EiaDownloadedWorkbook:
    """Download a trusted workbook using a caller-owned HTTP client.

    Requests are streamed and bounded by a maximum response size.
    Redirects are refused, even if the supplied client allows them.

    The caller owns client lifecycle. This function does not retry,
    update caches, or interpret spreadsheet observations.
    """

    url = _trusted_workbook_url(region)

    if not isinstance(client, httpx.Client):
        raise TypeError("client must be an httpx.Client")

    if limits is None:
        limits = EiaRetrievalLimits()

    if not isinstance(limits, EiaRetrievalLimits):
        raise TypeError("limits must be an EiaRetrievalLimits")

    timeout = httpx.Timeout(
        connect=limits.connect_timeout_seconds,
        read=limits.read_timeout_seconds,
        write=limits.read_timeout_seconds,
        pool=limits.connect_timeout_seconds,
    )

    content = bytearray()

    try:
        with client.stream(
            "GET",
            url,
            follow_redirects=False,
            timeout=timeout,
            headers={"Accept": "application/vnd.ms-excel, */*"},
        ) as response:
            status = response.status_code

            if 300 <= status < 400:
                raise EiaRetrievalError(
                    EiaRetrievalFailureReason.UNSAFE_REDIRECT,
                    status_code=status,
                )

            if status < 200 or status >= 300:
                raise EiaRetrievalError(
                    EiaRetrievalFailureReason.HTTP_ERROR,
                    status_code=status,
                )

            declared_length = response.headers.get("content-length")

            if declared_length is not None:
                try:
                    length = int(declared_length)
                except ValueError:
                    raise EiaRetrievalError(EiaRetrievalFailureReason.INVALID_CONTENT) from None

                if length < 0:
                    raise EiaRetrievalError(EiaRetrievalFailureReason.INVALID_CONTENT)

                if length > limits.max_download_bytes:
                    raise EiaRetrievalError(EiaRetrievalFailureReason.DOWNLOAD_TOO_LARGE)

            for chunk in response.iter_bytes(chunk_size=DOWNLOAD_CHUNK_BYTES):
                if len(content) + len(chunk) > limits.max_download_bytes:
                    raise EiaRetrievalError(EiaRetrievalFailureReason.DOWNLOAD_TOO_LARGE)

                content.extend(chunk)

    except httpx.TimeoutException:
        raise EiaRetrievalError(EiaRetrievalFailureReason.TIMEOUT) from None
    except httpx.RequestError:
        raise EiaRetrievalError(EiaRetrievalFailureReason.NETWORK_ERROR) from None

    if not content:
        raise EiaRetrievalError(EiaRetrievalFailureReason.EMPTY_RESPONSE)

    if not content.startswith(XLS_SIGNATURE):
        raise EiaRetrievalError(EiaRetrievalFailureReason.INVALID_CONTENT)

    return EiaDownloadedWorkbook(
        source_url=url,
        content=bytes(content),
    )
