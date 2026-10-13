"""Provider-neutral boundary and failures for elevation acquisition."""

from collections.abc import Sequence
from typing import Protocol

from routevalue.application.terrain import ElevationSample
from routevalue.application.terrain_sampling import TerrainSampleLocation


class ElevationProviderError(RuntimeError):
    """Base failure for retrieving elevations from an external provider."""


class ElevationProviderUnavailableError(ElevationProviderError):
    """The provider could not service an elevation request."""


class ElevationProviderQuotaError(ElevationProviderUnavailableError):
    """The provider reported an elevation request quota or rate limit."""


class ElevationProviderRejectedError(ElevationProviderError):
    """The provider rejected an elevation request as invalid or unauthorized."""


class ElevationProviderResponseError(ElevationProviderError):
    """The provider returned elevation data that could not be trusted."""


class ElevationProvider(Protocol):
    """Retrieve observations for one bounded batch of route-aligned coordinates."""

    def get_elevations(
        self,
        locations: Sequence[TerrainSampleLocation],
    ) -> tuple[ElevationSample, ...]:
        """Return exactly one observation per location in the same order."""
        ...
