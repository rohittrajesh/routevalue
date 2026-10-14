"""Provider-neutral gasoline pricing geography and provenance."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class GasolinePriceGeographicScope(StrEnum):
    """Geographic granularity of an observed gasoline price."""

    NATIONAL = "national"
    REGION = "region"
    STATE = "state"
    METRO = "metro"
    STATION = "station"


@dataclass(frozen=True, slots=True)
class GasolinePriceGeography:
    """Normalized geographic identity for a gasoline price."""

    scope: GasolinePriceGeographicScope
    region_id: str
    display_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope, GasolinePriceGeographicScope):
            raise TypeError("scope must be a GasolinePriceGeographicScope")

        for field_name in ("region_id", "display_name"):
            value = getattr(self, field_name)

            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")

            if not value or not value.strip():
                raise ValueError(f"{field_name} cannot be blank")

            if value != value.strip():
                raise ValueError(f"{field_name} cannot have surrounding whitespace")


@dataclass(frozen=True, slots=True)
class GasolineMarketMetadata:
    """Source and geographic provenance for a market quote.

    The quote's observed_at remains the authoritative timestamp
    for fuel-price freshness calculations.

    published_at describes when the provider published the data.
    It does not replace the observation timestamp.
    """

    provider: str
    geography: GasolinePriceGeography
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str):
            raise TypeError("provider must be a string")

        if not self.provider or not self.provider.strip():
            raise ValueError("provider cannot be blank")

        if self.provider != self.provider.strip():
            raise ValueError("provider cannot have surrounding whitespace")

        if not isinstance(self.geography, GasolinePriceGeography):
            raise TypeError("geography must be a GasolinePriceGeography")

        if self.published_at is not None:
            if not isinstance(self.published_at, datetime):
                raise TypeError("published_at must be a datetime")

            if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
                raise ValueError("published_at must be timezone-aware")
