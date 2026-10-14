"""Trusted geographic jurisdiction resolution for gasoline pricing."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from routevalue.application.models import ResolvedLocation


class PricingJurisdiction(StrEnum):
    """Trusted geographic classification for a pricing reference."""

    CALIFORNIA = "california"
    OTHER_US = "other_us"
    OUTSIDE_US = "outside_us"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PricingJurisdictionResult:
    """Classification produced by a trusted geographic resolver."""

    jurisdiction: PricingJurisdiction

    def __post_init__(self) -> None:
        if not isinstance(self.jurisdiction, PricingJurisdiction):
            raise TypeError("jurisdiction must be a PricingJurisdiction")


class PricingJurisdictionResolver(Protocol):
    """Resolve coordinates using a trusted geographic source.

    Implementations must not trust display names or arbitrary
    client-supplied source identifiers as proof of jurisdiction.
    """

    def resolve(
        self,
        location: ResolvedLocation,
    ) -> PricingJurisdictionResult:
        """Return a trusted jurisdiction classification."""
        ...


class PricingGeographyUnavailableReason(StrEnum):
    """Reasons a pricing geography cannot be determined safely."""

    OUTSIDE_SUPPORTED_COUNTRY = "outside_supported_country"
    JURISDICTION_UNKNOWN = "jurisdiction_unknown"


class PricingGeographyUnavailableError(RuntimeError):
    """No verified geographic reference is available."""

    def __init__(
        self,
        reason: PricingGeographyUnavailableReason,
    ) -> None:
        if not isinstance(reason, PricingGeographyUnavailableReason):
            raise TypeError("reason must be a PricingGeographyUnavailableReason")

        self.reason = reason
        super().__init__(reason.value)


def resolve_pricing_jurisdiction(
    *,
    resolver: PricingJurisdictionResolver,
    location: ResolvedLocation,
) -> PricingJurisdiction:
    """Obtain one verified geographic classification.

    Coordinates must already be represented by ResolvedLocation.
    The supplied resolver owns jurisdiction determination.
    """

    if not isinstance(location, ResolvedLocation):
        raise TypeError("location must be a ResolvedLocation")

    result = resolver.resolve(location)

    if not isinstance(result, PricingJurisdictionResult):
        raise TypeError("resolver must return a PricingJurisdictionResult")

    jurisdiction = result.jurisdiction

    if jurisdiction is PricingJurisdiction.OUTSIDE_US:
        raise PricingGeographyUnavailableError(
            PricingGeographyUnavailableReason.OUTSIDE_SUPPORTED_COUNTRY
        )

    if jurisdiction is PricingJurisdiction.UNKNOWN:
        raise PricingGeographyUnavailableError(
            PricingGeographyUnavailableReason.JURISDICTION_UNKNOWN
        )

    return jurisdiction
