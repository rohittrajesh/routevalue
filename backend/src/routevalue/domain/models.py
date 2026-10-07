"""Core domain models for RouteValue."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from routevalue.domain.units import (
    Gallons,
    KilowattHours,
    KilowattHoursPerMile,
    Meters,
    MilesPerGallon,
    Money,
    MoneyPerGallon,
    MoneyPerKilowattHour,
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


class GasolineGrade(StrEnum):
    """Gasoline grade required by a gasoline vehicle."""

    REGULAR = "regular"
    MIDGRADE = "midgrade"
    PREMIUM = "premium"


@dataclass(frozen=True, slots=True)
class GasolineVehicleProfile:
    """Stable vehicle inputs required by gasoline energy models."""

    fuel_efficiency_mpg: MilesPerGallon
    fuel_grade: GasolineGrade

    def __post_init__(self) -> None:
        if self.fuel_efficiency_mpg <= 0:
            raise ValueError("fuel_efficiency_mpg must be greater than zero")


@dataclass(frozen=True, slots=True)
class GasolineVehicleSpecification:
    """Provider-neutral gasoline efficiency inputs for energy modeling."""

    combined_mpg: MilesPerGallon
    fuel_grade: GasolineGrade
    city_mpg: MilesPerGallon | None = None
    highway_mpg: MilesPerGallon | None = None

    def __post_init__(self) -> None:
        if self.combined_mpg <= 0:
            raise ValueError("combined_mpg must be greater than zero")

        if self.city_mpg is not None and self.city_mpg <= 0:
            raise ValueError("city_mpg must be greater than zero when provided")

        if self.highway_mpg is not None and self.highway_mpg <= 0:
            raise ValueError("highway_mpg must be greater than zero when provided")


@dataclass(frozen=True, slots=True)
class ElectricVehicleSpecification:
    """Provider-neutral battery-electric efficiency inputs for energy modeling."""

    combined_kwh_per_mile: KilowattHoursPerMile
    city_kwh_per_mile: KilowattHoursPerMile | None = None
    highway_kwh_per_mile: KilowattHoursPerMile | None = None

    def __post_init__(self) -> None:
        if self.combined_kwh_per_mile <= 0:
            raise ValueError("combined_kwh_per_mile must be greater than zero")

        if self.city_kwh_per_mile is not None and self.city_kwh_per_mile <= 0:
            raise ValueError("city_kwh_per_mile must be greater than zero when provided")

        if self.highway_kwh_per_mile is not None and self.highway_kwh_per_mile <= 0:
            raise ValueError("highway_kwh_per_mile must be greater than zero when provided")


type VehicleEnergySpecification = GasolineVehicleSpecification | ElectricVehicleSpecification


@dataclass(frozen=True, slots=True)
class GasolineConsumption:
    """Physical gasoline consumed by a route."""

    gallons: Gallons

    def __post_init__(self) -> None:
        if self.gallons < 0:
            raise ValueError("gallons cannot be negative")


@dataclass(frozen=True, slots=True)
class ElectricConsumption:
    """Physical electrical energy consumed by a route."""

    kilowatt_hours: KilowattHours

    def __post_init__(self) -> None:
        if self.kilowatt_hours < 0:
            raise ValueError("kilowatt_hours cannot be negative")


type EnergyConsumption = GasolineConsumption | ElectricConsumption


class GasolinePriceSource(StrEnum):
    """Source category for a gasoline price."""

    USER_OVERRIDE = "user_override"
    LOCAL_MARKET = "local_market"
    REGIONAL_MARKET = "regional_market"


FuelPriceSource = GasolinePriceSource


@dataclass(frozen=True, slots=True)
class GasolinePriceQuote:
    """A grade-specific gasoline price available to the domain."""

    price_per_gallon: MoneyPerGallon
    fuel_grade: GasolineGrade
    source: GasolinePriceSource
    observed_at: datetime | None

    def __post_init__(self) -> None:
        if self.price_per_gallon < 0:
            raise ValueError("price_per_gallon cannot be negative")

        if self.source is not GasolinePriceSource.USER_OVERRIDE and self.observed_at is None:
            raise ValueError("market fuel price requires an observation timestamp")

        if self.observed_at is not None and (
            self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be timezone-aware")


FuelPriceQuote = GasolinePriceQuote


@dataclass(frozen=True, slots=True)
class ElectricityPriceQuote:
    """Electricity price available to the domain."""

    price_per_kilowatt_hour: MoneyPerKilowattHour

    def __post_init__(self) -> None:
        if self.price_per_kilowatt_hour < 0:
            raise ValueError("price_per_kilowatt_hour cannot be negative")


type EnergyPriceQuote = GasolinePriceQuote | ElectricityPriceQuote


@dataclass(frozen=True, slots=True)
class EnergyEstimate:
    """Physical energy consumption and monetary energy cost for a route."""

    cost: Money
    consumption: EnergyConsumption | None = None

    def __post_init__(self) -> None:
        if self.cost < 0:
            raise ValueError("energy cost cannot be negative")


@dataclass(frozen=True, slots=True)
class DecisionCandidate:
    """An eligible route paired with the energy estimate used for decision-making."""

    route: RouteCandidate
    energy_estimate: EnergyEstimate

    def __post_init__(self) -> None:
        if self.route.toll_cost is None:
            raise ValueError("decision candidate requires known toll cost")


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """Authoritative generalized-cost components for one eligible route."""

    monetary_cost: Money
    time_cost: Money
    generalized_cost: Money

    def __post_init__(self) -> None:
        if self.monetary_cost < 0:
            raise ValueError("monetary_cost cannot be negative")

        if self.time_cost < 0:
            raise ValueError("time_cost cannot be negative")

        if self.generalized_cost != self.monetary_cost + self.time_cost:
            raise ValueError("generalized_cost must equal monetary_cost plus time_cost")


class IneligibilityReason(StrEnum):
    """Structured reason explaining why a route cannot enter normal optimization."""

    MISSING_TOLL_COST = "missing_toll_cost"
    MISSING_ENERGY_ESTIMATE = "missing_energy_estimate"


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    """Result of evaluating whether a route may enter normal optimization."""

    eligible: bool
    reason: IneligibilityReason | None

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
