"""HTTP request and response schemas for the RouteValue API."""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, field_validator


class GasolineGradeInput(StrEnum):
    """Gasoline grades accepted by the public V1 API."""

    REGULAR = "regular"
    MIDGRADE = "midgrade"
    PREMIUM = "premium"


class GasolineInputs(BaseModel):
    """Gasoline-specific personalization inputs for one trip evaluation."""

    fuel_efficiency_mpg: Decimal
    fuel_grade: GasolineGradeInput
    fuel_price_per_gallon: Decimal

    @field_validator("fuel_efficiency_mpg")
    @classmethod
    def fuel_efficiency_must_be_positive(cls, value: Decimal) -> Decimal:
        """Require a positive gasoline fuel-efficiency value."""

        if value <= 0:
            raise ValueError("fuel_efficiency_mpg must be greater than zero")

        return value

    @field_validator("fuel_price_per_gallon")
    @classmethod
    def fuel_price_cannot_be_negative(cls, value: Decimal) -> Decimal:
        """Reject negative user-supplied gasoline prices."""

        if value < 0:
            raise ValueError("fuel_price_per_gallon cannot be negative")

        return value


class TripEvaluationRequest(BaseModel):
    """HTTP request body for evaluating a trip."""

    origin: str
    destination: str
    value_of_time_per_hour: Decimal
    gasoline: GasolineInputs

    @field_validator("origin", "destination")
    @classmethod
    def endpoint_cannot_be_blank(cls, value: str) -> str:
        """Reject blank route endpoints without normalizing valid input."""

        if not value.strip():
            raise ValueError("route endpoint cannot be blank")

        return value

    @field_validator("value_of_time_per_hour")
    @classmethod
    def value_of_time_cannot_be_negative(cls, value: Decimal) -> Decimal:
        """Reject negative values of travel time."""

        if value < 0:
            raise ValueError("value_of_time_per_hour cannot be negative")

        return value


class RouteResponse(BaseModel):
    """Public representation of one normalized route."""

    distance_meters: int
    duration_seconds: int
    toll_cost: Decimal | None


class EnergyEstimateResponse(BaseModel):
    """Public representation of a route's monetary energy estimate."""

    cost: Decimal


class EligibilityResponse(BaseModel):
    """Public representation of route eligibility."""

    eligible: bool
    reason: str | None


class RouteEvaluationResponse(BaseModel):
    """Public evaluation details for one route."""

    route: RouteResponse
    energy_estimate: EnergyEstimateResponse | None
    eligibility: EligibilityResponse


class DecisionResponse(BaseModel):
    """Public representation of the final route decision."""

    recommended_route: RouteResponse | None
    reason: str | None
    numerical_tie: bool
    missing_data_present: bool
    candidate_count: int
    eligible_count: int


class TripEvaluationResponse(BaseModel):
    """HTTP response body for one trip evaluation."""

    route_evaluations: list[RouteEvaluationResponse]
    decision: DecisionResponse
