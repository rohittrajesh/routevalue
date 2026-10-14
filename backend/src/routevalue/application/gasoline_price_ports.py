"""Provider-neutral gasoline pricing lookup contracts."""

from dataclasses import dataclass
from typing import Protocol

from routevalue.domain.gasoline_price_metadata import (
    GasolinePriceGeography,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
)


@dataclass(frozen=True, slots=True)
class GasolinePriceLookupRequest:
    """One grade-specific lookup for one geographic scope.

    Geographic fallback and manual override precedence belong
    to application orchestration, not the provider adapter.
    """

    fuel_grade: GasolineGrade
    geography: GasolinePriceGeography

    def __post_init__(self) -> None:
        if not isinstance(self.fuel_grade, GasolineGrade):
            raise TypeError("fuel_grade must be a GasolineGrade")

        if not isinstance(self.geography, GasolinePriceGeography):
            raise TypeError("geography must be a GasolinePriceGeography")


class GasolinePriceProvider(Protocol):
    """Obtain normalized gasoline prices behind a provider-neutral port."""

    def get_price(
        self,
        request: GasolinePriceLookupRequest,
    ) -> GasolinePriceQuote | None:
        """Return a quote or None when no matching price exists.

        The returned quote must be normalized to the requested
        gasoline grade and geography.

        Provider failures must not be silently converted to None.
        """
        ...
