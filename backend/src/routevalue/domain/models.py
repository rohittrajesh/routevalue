"""Core domain models for RouteValue."""

from dataclasses import dataclass
from enum import StrEnum

from routevalue.domain.units import (
    Meters,
    MilesPerGallon,
    Money,
    MoneyPerGallon,
    Seconds,
)


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    """A normalized route candidate independent of any routing provider."""

    distance_meters: Meters
    duration_seconds: Seconds
    toll_cost: Money | None

    def __post_init__(self) -> None:
        if self.distance_meters < 0:
            raise ValueError("distance_meters cannot be negative")

        if self.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")

        if self.toll_cost is not None and self.toll_cost < 0:
            raise ValueError("toll_cost cannot be negative")

@dataclass(frozen=True, slots=True)
class VehicleProfile:
    """Vehicle inputs required by the V1 gasoline energy model."""

    fuel_efficiency_mpg: MilesPerGallon
    fuel_price_per_gallon: MoneyPerGallon

    def __post_init__(self) -> None:
        if self.fuel_efficiency_mpg <= 0:
            raise ValueError("fuel_efficiency_mpg must be greater than zero")

        if self.fuel_price_per_gallon < 0:
            raise ValueError("fuel_price_per_gallon cannot be negative")

@dataclass(frozen=True, slots=True)
class EnergyEstimate:
    """Estimated monetary energy cost for a route."""

    cost: Money

    def __post_init__(self) -> None:
        if self.cost < 0:
            raise ValueError("energy cost cannot be negative")

@dataclass(frozen=True, slots=True)
class DecisionCandidate:
    """A route paired with the energy estimate used for decision-making."""

    route: RouteCandidate
    energy_estimate: EnergyEstimate

@dataclass(frozen=True, slots=True)
class EligibilityResult:
    """Result of evaluating whether a route may enter normal optimization."""

    eligible: bool
    reason: str | None

    def __post_init__(self) -> None:
        if self.eligible and self.reason is not None:
            raise ValueError("eligible route cannot have an ineligibility reason")

        if not self.eligible and not self.reason:
            raise ValueError("ineligible route must have an ineligibility reason")

class DecisionReason(StrEnum):
    """Structured reason explaining why a route was selected."""

    CHEAPER_ROUTE_WORTH_EXTRA_TIME = "cheaper_route_worth_extra_time"
    FASTER_ROUTE_WORTH_EXTRA_COST = "faster_route_worth_extra_cost"
    FASTER_AND_CHEAPER = "faster_and_cheaper"
    NUMERICAL_TIE_FASTER_WINS = "numerical_tie_faster_wins"
    NUMERICAL_TIE_CHEAPER_WINS = "numerical_tie_cheaper_wins"
    NUMERICAL_TIE_SHORTER_DISTANCE_WINS = "numerical_tie_shorter_distance_wins"
    NUMERICAL_TIE_STABLE_ORDER_WINS = "numerical_tie_stable_order_wins"
    ONLY_ELIGIBLE_ROUTE = "only_eligible_route"

@dataclass(frozen=True, slots=True)
class DecisionResult:
    """Structured outcome of the RouteValue decision process."""

    recommended_route: RouteCandidate | None
    reason: DecisionReason | None
    numerical_tie: bool
    missing_data_present: bool
    candidate_count: int
    eligible_count: int

    def __post_init__(self) -> None:
        if self.candidate_count < 0:
            raise ValueError("candidate_count cannot be negative")

        if self.eligible_count < 0:
            raise ValueError("eligible_count cannot be negative")

        if self.eligible_count > self.candidate_count:
            raise ValueError("eligible_count cannot exceed candidate_count")

        if self.eligible_count == 0 and self.recommended_route is not None:
            raise ValueError("cannot recommend a route when no routes are eligible")

        if self.eligible_count > 0 and self.recommended_route is None:
            raise ValueError("recommended_route is required when eligible routes exist")

        if self.recommended_route is not None and self.reason is None:
            raise ValueError("recommended route requires a decision reason")

        if self.recommended_route is None and self.reason is not None:
            raise ValueError("decision reason requires a recommended route")