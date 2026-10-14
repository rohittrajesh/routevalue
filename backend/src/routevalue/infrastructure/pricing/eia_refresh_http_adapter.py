"""HTTP adapter for the controlled EIA gasoline refresh coordinator.

The caller owns the HTTP client and is responsible for closing it.
The adapter delegates all retrieval safety checks to the existing
bounded EIA XLS downloader.
"""

from dataclasses import dataclass

import httpx

from routevalue.infrastructure.pricing.eia_geography import (
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_retrieval_models import (
    EiaRetrievalLimits,
)
from routevalue.infrastructure.pricing.eia_xls_downloader import (
    download_eia_xls_workbook,
)


@dataclass(frozen=True, slots=True)
class EiaWorkbookFetcher:
    """Adapt validated EIA workbook downloads to raw XLS bytes."""

    client: httpx.Client
    limits: EiaRetrievalLimits | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.client, httpx.Client):
            raise TypeError("client must be an httpx.Client")

        if self.limits is not None and not isinstance(self.limits, EiaRetrievalLimits):
            raise TypeError("limits must be EiaRetrievalLimits or None")

    def __call__(self, region: EiaGasolineRegion) -> bytes:
        """Download one trusted EIA XLS workbook.

        The underlying downloader validates the source, HTTP response,
        size limit, redirect policy, and XLS binary signature.
        """

        workbook = download_eia_xls_workbook(
            region=region,
            client=self.client,
            limits=self.limits,
        )

        return workbook.content
