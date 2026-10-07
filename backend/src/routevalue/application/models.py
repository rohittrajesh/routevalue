"""Application-layer models for RouteValue use cases."""

from dataclasses import dataclass
from enum import StrEnum

from routevalue.domain.models import (
    CostBreakdown,
    DecisionResult,
    EligibilityResult,
    EnergyEstimate,
    RouteCandidate,
    VehicleEnergySpecification,
)


@dataclass(frozen=True, slots=True)
class ResolvedLocation:
    """Provider-neutral resolved location for routing."""

    display_name: str
    latitude: float
    longitude: float
    source: str | None = None
    source_id: str | None = None

    def __post_init__(self) -> None:
        if not self.display_name.strip():
            raise ValueError("display_name cannot be blank")

        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")

        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")

        if (self.source is None) != (self.source_id is None):
            raise ValueError("source and source_id must be provided together")

        if self.source is not None and not self.source.strip():
            raise ValueError("source cannot be blank")

        if self.source_id is not None and not self.source_id.strip():
            raise ValueError("source_id cannot be blank")


@dataclass(frozen=True, slots=True)
class RoutePoint:
    """One provider-neutral latitude/longitude point along a route."""

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")

        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")


@dataclass(frozen=True, slots=True)
class RouteGeometry:
    """Provider-neutral ordered geometry for one complete route."""

    points: tuple[RoutePoint, ...]

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("route geometry requires at least two points")


@dataclass(frozen=True, slots=True)
class ProvidedRoute:
    """A normalized route candidate with optional presentation geometry."""

    route: RouteCandidate
    geometry: RouteGeometry | None = None


@dataclass(frozen=True, slots=True)
class RouteSearchRequest:
    """Provider-neutral request for candidate routes between two locations."""

    origin: ResolvedLocation
    destination: ResolvedLocation


@dataclass(frozen=True, slots=True)
class VehicleCatalogConfiguration:
    """One provider-neutral selectable vehicle configuration."""

    year: int
    make: str
    model: str
    configuration: str
    source: str
    source_id: str

    def __post_init__(self) -> None:
        if self.year <= 0:
            raise ValueError("year must be greater than zero")

        if not self.make.strip():
            raise ValueError("make cannot be blank")

        if not self.model.strip():
            raise ValueError("model cannot be blank")

        if not self.configuration.strip():
            raise ValueError("configuration cannot be blank")

        if not self.source.strip():
            raise ValueError("source cannot be blank")

        if not self.source_id.strip():
            raise ValueError("source_id cannot be blank")


class VehicleSpecificationUnavailableReason(StrEnum):
    """Structured reason a catalog configuration cannot yield a supported specification."""

    UNSUPPORTED_POWERTRAIN = "unsupported_powertrain"
    MISSING_REQUIRED_DATA = "missing_required_data"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class VehicleSpecificationLookupResult:
    """Provider-neutral result of resolving one catalog configuration."""

    specification: VehicleEnergySpecification | None
    unavailable_reason: VehicleSpecificationUnavailableReason | None

    def __post_init__(self) -> None:
        if (self.specification is None) == (self.unavailable_reason is None):
            raise ValueError(
                "vehicle specification lookup result requires exactly one of "
                "specification or unavailable_reason"
            )


@dataclass(frozen=True, slots=True)
class RouteEvaluation:
    """Application-level evaluation details for one candidate route."""

    route: RouteCandidate
    energy_estimate: EnergyEstimate | None
    eligibility: EligibilityResult
    cost_breakdown: CostBreakdown | None
    geometry: RouteGeometry | None = None

    def __post_init__(self) -> None:
        if self.eligibility.eligible and self.cost_breakdown is None:
            raise ValueError("eligible route requires a cost breakdown")

        if not self.eligibility.eligible and self.cost_breakdown is not None:
            raise ValueError("ineligible route cannot have a cost breakdown")


@dataclass(frozen=True, slots=True)
class TripEvaluationResult:
    """Complete application-level result for evaluating one trip."""

    route_evaluations: tuple[RouteEvaluation, ...]
    decision: DecisionResult

    def __post_init__(self) -> None:
        if len(self.route_evaluations) != self.decision.candidate_count:
            raise ValueError("route evaluation count must match decision candidate count")

        eligible_count = sum(
            evaluation.eligibility.eligible for evaluation in self.route_evaluations
        )

        if eligible_count != self.decision.eligible_count:
            raise ValueError("eligible route evaluation count must match decision eligible count")

        missing_data_present = any(
            not evaluation.eligibility.eligible for evaluation in self.route_evaluations
        )
        if missing_data_present != self.decision.missing_data_present:
            raise ValueError("route evaluation missing-data state must match decision")
